export function extractYoutubeVideoId(url) {
  if (!url) return null;
  
  // Regular expression to match various YouTube URL formats:
  // - youtube.com/watch?v=ID
  // - youtu.be/ID
  // - youtube.com/embed/ID
  // - youtube.com/shorts/ID
  // - m.youtube.com/...
  const pattern = /(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?.*v=|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
  const match = url.match(pattern);
  
  return match ? match[1] : null;
}
