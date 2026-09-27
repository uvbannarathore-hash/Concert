import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';

export default function TrailerModal({ videoId, onClose }) {
  useEffect(() => {
    // Add escape key listener to close modal
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    
    // Prevent background scrolling while modal is open
    document.body.style.overflow = 'hidden';
    
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [onClose]);

  if (!videoId) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-void/90 backdrop-blur-sm animate-fade-in">
      <div 
        className="absolute inset-0" 
        onClick={onClose}
        aria-label="Close modal"
      />
      
      <div className="relative w-full max-w-4xl aspect-video bg-void rounded-xl overflow-hidden shadow-2xl z-10 border border-white/[0.05]">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-20 bg-void/60 hover:bg-spot text-white p-2 rounded-full backdrop-blur-sm transition-all"
          aria-label="Close trailer"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
        
        {/* We use key={videoId} to force unmount/remount if videoId changes, though conditionally rendering the iframe unmounts it entirely when closed */}
        <iframe
          key={videoId}
          src={`https://www.youtube.com/embed/${videoId}?autoplay=1&rel=0`}
          title="Event Trailer"
          className="w-full h-full border-0"
          allow="autoplay; encrypted-media; picture-in-picture"
          allowFullScreen
        ></iframe>
      </div>
    </div>,
    document.body
  );
}
