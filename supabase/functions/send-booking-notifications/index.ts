// supabase/functions/send-booking-notifications/index.ts
//
// This runs on Supabase's own infrastructure (Deno-based Edge Functions) -
// NOT n8n. It's triggered by a Supabase Database Webhook whenever a row
// in `bookings` is updated. No n8n execution is consumed for this at all.

import { serve } from "https://deno.land/std@0.203.0/http/server.ts";
import { SMTPClient } from "https://deno.land/x/denomailer@1.6.0/mod.ts";

const TELEGRAM_BOT_TOKEN = Deno.env.get("TELEGRAM_BOT_TOKEN")!;
const GMAIL_ADDRESS = Deno.env.get("GMAIL_ADDRESS")!;         // your full gmail address, e.g. yourname@gmail.com
const GMAIL_APP_PASSWORD = Deno.env.get("GMAIL_APP_PASSWORD")!; // the 16-character App Password (not your normal password)
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const WEBHOOK_SHARED_SECRET = Deno.env.get("DB_WEBHOOK_SHARED_SECRET")!; // set this yourself, must match the header configured on the Database Webhook

serve(async (req) => {
  try {
    // 1. Verify the request actually came from our own Supabase Database Webhook,
    //    not some random caller hitting this public URL.
    const incomingSecret = req.headers.get("x-webhook-secret");
    if (incomingSecret !== WEBHOOK_SHARED_SECRET) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });
    }

    const payload = await req.json();
    const record = payload.record;      // the new row state
    const oldRecord = payload.old_record; // the previous row state

    // 2. Only act when status just transitioned INTO "Confirmed", "Cancelled",
    //    or when reminder_sent transitioned to true.
    const justConfirmed =
      record?.status === "Confirmed" && oldRecord?.status !== "Confirmed" && payload.table === "bookings";

    const justCancelled =
      record?.status === "Cancelled" && oldRecord?.status !== "Cancelled" && payload.table === "bookings";

    const justReminded =
      record?.reminder_sent === true && oldRecord?.reminder_sent !== true && payload.table === "bookings";
      
    const justNotifiedSeatUpgrade =
      record?.status === "notified" && oldRecord?.status !== "notified" && payload.table === "seat_upgrade_requests";

    if (!justConfirmed && !justCancelled && !justReminded && !justNotifiedSeatUpgrade) {
      return new Response(JSON.stringify({ skipped: true }), { status: 200 });
    }

    // 3. Look up the user (chat_id, email, telegram preference) using the
    //    service role key (server-side only, never exposed to the browser).
    const userRes = await fetch(
      `${SUPABASE_URL}/rest/v1/users?user_id=eq.${record.user_id}&select=telegram_chat_id,email,name,notify_telegram_for_website`,
      {
        headers: {
          apikey: SUPABASE_SERVICE_ROLE_KEY,
          Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
        },
      }
    );
    const users = await userRes.json();
    const user = Array.isArray(users) ? users[0] : null;

    // 3b. Look up event details (bookings only stores event_id, not the name)
    const eventRes = await fetch(
      `${SUPABASE_URL}/rest/v1/events?event_id=eq.${record.event_id}&select=artist_name,venue_name,event_date,event_time`,
      {
        headers: {
          apikey: SUPABASE_SERVICE_ROLE_KEY,
          Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
        },
      }
    );
    const events = await eventRes.json();
    const event = Array.isArray(events) ? events[0] : null;

    const eventLine = event
      ? `Event: ${event.artist_name}${event.venue_name ? ` @ ${event.venue_name}` : ""}${event.event_date ? ` on ${event.event_date}` : ""}\n`
      : "";

    let subject = "";
    let emailHtml = "";
    let telegramMessage = "";

    if (justConfirmed) {
      subject = "Your booking is confirmed!";
      telegramMessage = `Your booking is confirmed!\n\n${eventLine}Booking ID: ${record.booking_id}\nCategory: ${record.category}\nSeats: ${record.seats_booked}\n\nSee you at the show!`;
      emailHtml = `
        <h2>Booking Confirmed</h2>
        <p>Hi ${user?.name || "there"},</p>
        <p>Your booking is confirmed. Details:</p>
        <ul>
          ${event ? `<li><strong>Event:</strong> ${event.artist_name}${event.venue_name ? ` @ ${event.venue_name}` : ""}</li>` : ""}
          <li><strong>Booking ID:</strong> ${record.booking_id}</li>
          <li><strong>Category:</strong> ${record.category}</li>
          <li><strong>Seats:</strong> ${record.seats_booked}</li>
        </ul>
        <p>See you at the show!</p>
      `;
    } else if (justCancelled) {
      const details = record.refund_details || {};
      const eligibleAmount = details.eligible_amount || 0;
      const cancellationFee = details.cancellation_fee_percentage || 0;
      const refundPercentage = details.refund_percentage || 0;
      const refundAmount = details.refund_amount || 0;
      const refundStatus = record.payment_status;

      subject = "Your booking has been cancelled";
      telegramMessage = `Your booking has been cancelled.\n\n${eventLine}Booking ID: ${record.booking_id}\n\nRefund Status: ${refundStatus}\nRefund Amount: ₹${refundAmount}`;
      // Build a status‑specific message for the email
      let refundMessage = "";
      switch (refundStatus) {
        case "Refunded":
        case "Refund Completed":
          refundMessage = `Your refund of ₹${refundAmount} has been processed successfully.`;
          break;
        case "Refund Pending":
        case "Refund Initiated":
          refundMessage = `Your refund of ₹${refundAmount} is being processed and will reflect in your account soon.`;
          break;
        case "Refund Failed":
          refundMessage = `We attempted to process a refund of ₹${refundAmount}, but it failed. Our support team will contact you shortly.`;
          break;
        default:
          refundMessage = `Refund status: ${refundStatus}.`;
      }
      emailHtml = `
        <h2>Booking Cancelled</h2>
        <p>Hi ${user?.name || "there"},</p>
        <p>Your booking has been cancelled. Details:</p>
        <ul>
          ${event ? `<li><strong>Event:</strong> ${event.artist_name}${event.venue_name ? ` @ ${event.venue_name}` : ""}</li>` : ""}
          <li><strong>Booking ID:</strong> ${record.booking_id}</li>
          <li><strong>Eligible Amount:</strong> ₹${eligibleAmount}</li>
          <li><strong>Cancellation Fee:</strong> ${cancellationFee}%</li>
          <li><strong>Refund Percentage:</strong> ${refundPercentage}%</li>
          <li><strong>Refund Amount:</strong> ₹${refundAmount}</li>
          <li><strong>Refund Status:</strong> ${refundStatus}</li>
        </ul>
        <p>${refundMessage}</p>
      `;
    } else if (justReminded) {
      subject = "Reminder: Your upcoming event is tomorrow!";
      telegramMessage = `Reminder: Your upcoming event is tomorrow!\n\n${eventLine}Booking ID: ${record.booking_id}\nCategory: ${record.category}\nSeats: ${record.seats_booked}\n\nGet ready for an amazing experience!`;
      emailHtml = `
        <h2>Event Reminder</h2>
        <p>Hi ${user?.name || "there"},</p>
        <p>This is a quick reminder that your event is coming up tomorrow! Details:</p>
        <ul>
          ${event ? `<li><strong>Event:</strong> ${event.artist_name}${event.venue_name ? ` @ ${event.venue_name}` : ""}</li>` : ""}
          <li><strong>Booking ID:</strong> ${record.booking_id}</li>
          <li><strong>Category:</strong> ${record.category}</li>
          <li><strong>Seats:</strong> ${record.seats_booked}</li>
        </ul>
        <p>Get ready for an amazing experience! See you there.</p>
      `;
    } else if (justNotifiedSeatUpgrade) {
      subject = "Good news! Seats available for upgrade";
      telegramMessage = `Good news! ${record.desired_category} seats are now available for your booking.\n\n${eventLine}You currently have ${record.current_category} tickets (Booking: ${record.original_booking_id}).\n\nReply 'Upgrade my booking' to claim the upgrade. Availability is subject to change.`;
      emailHtml = `
        <h2>Seat Upgrade Available</h2>
        <p>Hi ${user?.name || "there"},</p>
        <p>Good news! <strong>${record.desired_category}</strong> seats are now available for your booking.</p>
        <ul>
          ${event ? `<li><strong>Event:</strong> ${event.artist_name}${event.venue_name ? ` @ ${event.venue_name}` : ""}</li>` : ""}
          <li><strong>Booking ID:</strong> ${record.original_booking_id}</li>
          <li><strong>Current Category:</strong> ${record.current_category}</li>
          <li><strong>Desired Category:</strong> ${record.desired_category}</li>
        </ul>
        <p>Reply "Upgrade my booking" in the chat to claim this upgrade. Please note that availability is subject to change until you confirm.</p>
      `;
    }

    const tasks: Promise<Response>[] = [];

    // 4. Telegram notification - only when:
    //    a) the booking itself was made via Telegram, OR
    //    b) the user has explicitly opted in to also get Telegram
    //       notifications for bookings made on the website.
    const shouldSendTelegram =
      !!user?.telegram_chat_id &&
      (record.booking_source === "telegram" || user?.notify_telegram_for_website === true);

    if (shouldSendTelegram) {
      tasks.push(
        fetch(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chat_id: user.telegram_chat_id,
            text: telegramMessage,
          }),
        })
      );
    }

    // 5. Email notification via Gmail SMTP (only if we have an email on file)
    if (user?.email) {
      const client = new SMTPClient({
        connection: {
          hostname: "smtp.gmail.com",
          port: 465,
          tls: true,
          auth: {
            username: GMAIL_ADDRESS,
            password: GMAIL_APP_PASSWORD,
          },
        },
      });

      tasks.push(
        client
          .send({
            from: GMAIL_ADDRESS,
            to: user.email,
            subject: subject,
            html: emailHtml,
          })
          .then(() => client.close())
          .then(() => new Response("ok")) // keep return type consistent with the Telegram fetch task
      );
    }

    await Promise.allSettled(tasks);

    return new Response(JSON.stringify({ success: true }), { status: 200 });
  } catch (err) {
    console.error(err);
    return new Response(JSON.stringify({ error: String(err) }), { status: 500 });
  }
});