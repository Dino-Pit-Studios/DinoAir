import { useContext } from 'react';

import AnnouncementContext, { AnnouncementContextValue } from '../contexts/AnnouncementContext';

/**
 * Custom hook to access the announcement context
 * Provides typed methods for common announcements
 * @throws Error if used outside of AnnouncementProvider
 */
export const useAnnouncement = (): AnnouncementContextValue => {
  const context = useContext(AnnouncementContext);

  if (!context) {
    throw new Error('useAnnouncement must be used within an AnnouncementProvider');
  }

  return context;
};

// Re-export types for convenience
export type {
  Announcement,
  AnnouncementType,
  AnnouncementPoliteness,
  AnnouncementContextValue,
} from '../contexts/AnnouncementContext';
