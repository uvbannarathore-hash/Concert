// supabase/functions/send-booking-notifications/index.ts
//
// This runs on Supabase's own infrastructure (Deno-based Edge Functions) -
// NOT n8n. It is triggered by a Supabase Database Webhook for status updates
// (Confirmed, Cancelled, Seat Upgrades), OR directly via a pg_net scheduler
// invocation for Phase 3 Abandoned Checkouts. No n8n execution is consumed.

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
    // 1. Verify the request actually came from our own Supabase Database Webhook OR secure pg_net cron
    const incomingSecret = req.headers.get("x-webhook-secret");
    if (incomingSecret !== WEBHOOK_SHARED_SECRET) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });
    }

    const payload = await req.json();
    let record;
    let oldRecord = null;
    let isAbandonedSchedulerPayload = false;
    let isReminderSchedulerPayload = false;
    let aiContent = "";

    // 2a. Explicit Scheduler Routing
    if (payload.type === "abandoned_checkout" && payload.booking_id) {
      isAbandonedSchedulerPayload = true;
    } else if (payload.type === "event_reminder" && payload.booking_id) {
      isReminderSchedulerPayload = true;
      aiContent = payload.ai_content || "";
    }

    if (isAbandonedSchedulerPayload || isReminderSchedulerPayload) {
      const bookingRes = await fetch(
        `${SUPABASE_URL}/rest/v1/bookings?booking_id=eq.${payload.booking_id}&select=*`,
        {
          headers: {
            apikey: SUPABASE_SERVICE_ROLE_KEY,
            Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
          },
        }
      );
      const bookings = await bookingRes.json();
      record = Array.isArray(bookings) ? bookings[0] : null;

      if (isAbandonedSchedulerPayload) {
        if (!record || record.status !== "Pending" || record.payment_status !== "Pending") {
          return new Response(JSON.stringify({ skipped: true, reason: "No longer pending" }), { status: 200 });
        }
      } else if (isReminderSchedulerPayload) {
        if (!record || record.status !== "Confirmed" || record.payment_status !== "Paid") {
          return new Response(JSON.stringify({ skipped: true, reason: "Not confirmed or paid" }), { status: 200 });
        }
      }
    } else {
      // 2b. Standard Database Webhook Routing
      record = payload.record;
      oldRecord = payload.old_record;
    }

    const justConfirmed = !isAbandonedSchedulerPayload && !isReminderSchedulerPayload && record?.status === "Confirmed" && oldRecord?.status !== "Confirmed" && payload.table === "bookings";
    const justCancelled = !isAbandonedSchedulerPayload && !isReminderSchedulerPayload && record?.status === "Cancelled" && oldRecord?.status !== "Cancelled" && payload.table === "bookings";
    const justReminded = !isAbandonedSchedulerPayload && !isReminderSchedulerPayload && record?.reminder_sent === true && oldRecord?.reminder_sent !== true && payload.table === "bookings";
    const justNotifiedSeatUpgrade = !isAbandonedSchedulerPayload && !isReminderSchedulerPayload && record?.status === "notified" && oldRecord?.status !== "notified" && payload.table === "seat_upgrade_requests";

    if (!justConfirmed && !justCancelled && !justReminded && !justNotifiedSeatUpgrade && !isAbandonedSchedulerPayload && !isReminderSchedulerPayload) {
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
    } else if (isAbandonedSchedulerPayload) {
      const frontendUrl = Deno.env.get("FRONTEND_URL");
      if (!frontendUrl) {
        console.error("Configuration Error: FRONTEND_URL is missing in Edge Function environment. Omitting checkout CTA link from email.");
      }
      subject = "Your booking is still pending — complete your payment";
      telegramMessage = `You have a pending booking!\n\n${eventLine}Your seats are still held! Please complete your payment before they are released.\n\nBooking ID: ${record.booking_id}\nCategory: ${record.category}\nSeats: ${record.seats_booked}`;
      emailHtml = `
        <h2>Complete your payment</h2>
        <p>Hi ${user?.name || "there"},</p>
        <p>You have a pending booking. Your seats are still held!</p>
        <ul>
          ${event ? `<li><strong>Event:</strong> ${event.artist_name}${event.venue_name ? ` @ ${event.venue_name}` : ""}</li>` : ""}
          <li><strong>Booking ID:</strong> ${record.booking_id}</li>
          <li><strong>Category:</strong> ${record.category}</li>
          <li><strong>Seats:</strong> ${record.seats_booked}</li>
        </ul>
        <p>Please complete your payment before the seats are released.</p>
        ${frontendUrl ? `<p><a href="${frontendUrl}/bookings" style="display:inline-block;padding:10px 20px;background:#007BFF;color:#fff;text-decoration:none;border-radius:5px;">Complete Payment</a></p>` : ""}
      `;
    } else if (isReminderSchedulerPayload) {
      subject = `Get ready for ${event?.artist_name} tomorrow!`;
      telegramMessage = `Reminder: Your upcoming event is tomorrow!\n\n${eventLine}Booking ID: ${record.booking_id}\nCategory: ${record.category}\nSeats: ${record.seats_booked}\n\n${aiContent}`;
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
        <p><strong>Prep Guide:</strong></p>
        <p>${aiContent.replace(/\n/g, "<br>")}</p>
        <p>Get ready for an amazing experience! See you there.</p>
      `;
    }

    const tasks: Promise<Response>[] = [];

    // 4. Telegram notification - Generic Flow
    const shouldSendTelegram =
      !!user?.telegram_chat_id &&
      (record.booking_source === "telegram" || user?.notify_telegram_for_website === true) &&
      !isAbandonedSchedulerPayload && !isReminderSchedulerPayload;

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

    // 5. Email notification - Generic Flow
    const shouldSendEmail = !!user?.email && !isAbandonedSchedulerPayload && !isReminderSchedulerPayload;

    if (shouldSendEmail) {
      const client = new SMTPClient({
        connection: {
          hostname: "smtp.gmail.com",
          port: 465,
          tls: true,
          auth: { username: GMAIL_ADDRESS, password: GMAIL_APP_PASSWORD },
        },
      });

      tasks.push(
        client.send({ from: GMAIL_ADDRESS, to: user.email, subject: subject, html: emailHtml })
          .then(() => client.close())
          .then(() => new Response("ok"))
      );
    }

    // 6. Abandoned Checkout - Independent Idempotent Delivery
    if (isAbandonedSchedulerPayload) {
      const updateFlag = async (flag: string, val: boolean) => {
        return fetch(`${SUPABASE_URL}/rest/v1/bookings?booking_id=eq.${record.booking_id}`, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
          },
          body: JSON.stringify({ [flag]: val }),
        });
      };

      const handleIndependentChannel = async (flag: string, hasContact: boolean, sendFn: () => Promise<any>) => {
        if (!hasContact) {
          // Permanently skip if missing contact info
          await updateFlag(flag, true);
          return;
        }
        
        // Optimistic concurrency claim: only update if currently false
        const claimRes = await fetch(`${SUPABASE_URL}/rest/v1/bookings?booking_id=eq.${record.booking_id}&${flag}=eq.false`, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
            "Prefer": "return=representation" // Return updated rows
          },
          body: JSON.stringify({ [flag]: true }),
        });
        
        const claimedRows = await claimRes.json();
        if (!Array.isArray(claimedRows) || claimedRows.length === 0) {
          // Already sent or claimed by another concurrent execution
          return;
        }
        
        try {
          await sendFn();
        } catch (e) {
          // Revert claim on failure to allow retry
          await updateFlag(flag, false);
          throw e;
        }
      };

      if (!record.abandoned_telegram_sent) {
        tasks.push(handleIndependentChannel("abandoned_telegram_sent", !!user?.telegram_chat_id, async () => {
          const res = await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ chat_id: user.telegram_chat_id, text: telegramMessage }),
          });
          if (!res.ok) throw new Error("Telegram failed");
        }));
      }

      if (!record.abandoned_email_sent) {
        tasks.push(handleIndependentChannel("abandoned_email_sent", !!user?.email, async () => {
          const client = new SMTPClient({
            connection: {
              hostname: "smtp.gmail.com",
              port: 465,
              tls: true,
              auth: { username: GMAIL_ADDRESS, password: GMAIL_APP_PASSWORD },
            },
          });
          await client.send({ from: GMAIL_ADDRESS, to: user.email, subject: subject, html: emailHtml });
          await client.close();
        }));
      }
    }

    // 7. Event Reminder Delivery & State
    if (isReminderSchedulerPayload) {
      // Concurrency claim with 30-minute stale recovery AND independent channel check
      const thirtyMinsAgo = new Date(Date.now() - 30 * 60000).toISOString();
      const claimRes = await fetch(`${SUPABASE_URL}/rest/v1/bookings?booking_id=eq.${record.booking_id}&and=(or(reminder_email_sent.eq.false,reminder_telegram_sent.eq.false),or(reminder_claimed_at.is.null,reminder_claimed_at.lt.${thirtyMinsAgo}))`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "apikey": SUPABASE_SERVICE_ROLE_KEY,
          "Authorization": `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
          "Prefer": "return=representation"
        },
        body: JSON.stringify({ reminder_claimed_at: new Date().toISOString() }),
      });
      
      const claimedRows = await claimRes.json();
      if (!Array.isArray(claimedRows) || claimedRows.length === 0) {
        return new Response(JSON.stringify({ skipped: true, reason: "Already sent or claimed by another process recently" }), { status: 200 });
      }

      const shouldSendTel = !!user?.telegram_chat_id && (record.booking_source === "telegram" || user?.notify_telegram_for_website === true);
      const shouldSendEm = !!user?.email;

      let telSucceeded = !shouldSendTel || record.reminder_telegram_sent;
      let emSucceeded = !shouldSendEm || record.reminder_email_sent;

      const updateFlag = async (flag: string, val: any) => {
        const res = await fetch(`${SUPABASE_URL}/rest/v1/bookings?booking_id=eq.${record.booking_id}`, {
          method: "PATCH", headers: { "Content-Type": "application/json", "apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": `Bearer ${SUPABASE_SERVICE_ROLE_KEY}` },
          body: JSON.stringify({ [flag]: val }),
        });
        if (!res.ok) {
          throw new Error(`Failed to update ${flag} to ${val}`);
        }
        return res;
      };

      if (shouldSendTel && !record.reminder_telegram_sent) {
        try {
          const res = await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`, {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ chat_id: user.telegram_chat_id, text: telegramMessage }),
          });
          if (!res.ok) throw new Error("Telegram failed");
          await updateFlag("reminder_telegram_sent", true);
          telSucceeded = true;
        } catch (e) { console.error("Reminder Tel fail:", e); }
      }

      if (shouldSendEm && !record.reminder_email_sent) {
        try {
          const client = new SMTPClient({ connection: { hostname: "smtp.gmail.com", port: 465, tls: true, auth: { username: GMAIL_ADDRESS, password: GMAIL_APP_PASSWORD } } });
          await client.send({ from: GMAIL_ADDRESS, to: user.email, subject: subject, html: emailHtml });
          await client.close();
          await updateFlag("reminder_email_sent", true);
          emSucceeded = true;
        } catch (e) { console.error("Reminder Email fail:", e); }
      }

      if (telSucceeded && emSucceeded) {
        // Overall success: all eligible channels succeeded (or were already sent)
        await updateFlag("reminder_sent", true);
        return new Response(JSON.stringify({ success: true, finished: true }), { status: 200 });
      } else {
        // Release claim for retry on failures
        await updateFlag("reminder_claimed_at", null);
        return new Response(JSON.stringify({ error: "One or more channels failed" }), { status: 500 });
      }
    }

    await Promise.allSettled(tasks);

    return new Response(JSON.stringify({ success: true }), { status: 200 });
  } catch (err) {
    console.error(err);
    return new Response(JSON.stringify({ error: String(err) }), { status: 500 });
  }
});