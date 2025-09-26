import {
  createContext,
  useCallback,
  useEffect,
  useRef,
  useState,
  type FC,
  type ReactNode,
} from 'react';

// Types for announcement system
export type AnnouncementType = 'success' | 'error' | 'info' | 'warning' | 'status';
export type AnnouncementPoliteness = 'polite' | 'assertive' | 'off';

export interface Announcement {
  id: string;
  message: string;
  type: AnnouncementType;
  politeness: AnnouncementPoliteness;
  timestamp: number;
  duration?: number; // Duration in milliseconds before auto-clear
}

export interface AnnouncementContextValue {
  announcements: Announcement[];
  announce: (
    message: string,
    type?: AnnouncementType,
    politeness?: AnnouncementPoliteness,
    duration?: number
  ) => void;
  announceSuccess: (message: string, duration?: number) => void;
  announceError: (message: string, duration?: number) => void;
  announceInfo: (message: string, duration?: number) => void;
  announceWarning: (message: string, duration?: number) => void;
  announceStatus: (message: string, duration?: number) => void;
  clearAnnouncement: (id: string) => void;
  clearAllAnnouncements: () => void;
}

const AnnouncementContext = createContext<AnnouncementContextValue | undefined>(undefined);

interface AnnouncementProviderProps {
  children: ReactNode;
  defaultDuration?: number; // Default duration for auto-clear (ms)
}

/**
 * AnnouncementProvider component that supplies announcement context to its children.
 *
 * @param children - React child components that will have access to announcement context.
 * @param defaultDuration - Default duration in milliseconds before an announcement is auto-cleared (default is 5000ms).
 * @returns A context provider component for managing announcements.
 */
export const AnnouncementProvider: FC<AnnouncementProviderProps> = ({
  children,
  defaultDuration = 5000, // 5 seconds default
}) => {
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const timeoutRefs = useRef<Map<string, NodeJS.Timeout>>(new Map());

  // Clean up timeouts on unmount
  useEffect(() => {
    const map = timeoutRefs.current;
    return () => {
      map.forEach(timeout => clearTimeout(timeout));
      map.clear();
    };
  }, []);

  const clearAnnouncement = useCallback((id: string) => {
    setAnnouncements(prev => prev.filter(a => a.id !== id));
    const timeout = timeoutRefs.current.get(id);
    if (timeout) {
      clearTimeout(timeout);
      timeoutRefs.current.delete(id);
    }
  }, []);

  const clearAllAnnouncements = useCallback(() => {
    setAnnouncements([]);
    timeoutRefs.current.forEach(timeout => clearTimeout(timeout));
    timeoutRefs.current.clear();
  }, []);

  // Generate a robust unique ID for announcements
  const generateAnnouncementId = (): string => {
    const cryptoObj = (globalThis as unknown as { crypto?: Crypto }).crypto;
    if (cryptoObj?.randomUUID) {
      return `announcement-${cryptoObj.randomUUID()}`;
    }
    if (cryptoObj?.getRandomValues) {
      const bytes = new Uint8Array(16);
      cryptoObj.getRandomValues(bytes);
      let hex = '';
      for (const b of bytes) {
        hex += b.toString(16).padStart(2, '0');
      }
      return `announcement-${hex}`;
    }
    // Fallback: timestamp + random suffix (non-cryptographic)
    return `announcement-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  };
  const announce = useCallback(
    (
      message: string,
      type: AnnouncementType = 'info',
      politeness: AnnouncementPoliteness = 'polite',
      duration?: number
    ) => {
      const id = generateAnnouncementId();
      const announcement: Announcement = {
        id,
        message,
        type,
        politeness,
        timestamp: Date.now(),
        duration: duration ?? defaultDuration,
      };

      setAnnouncements(prev => [...prev, announcement]);

      // Set up auto-clear if duration is specified
      if (announcement.duration && announcement.duration > 0) {
        const timeout = setTimeout(() => {
          clearAnnouncement(id);
        }, announcement.duration);
        timeoutRefs.current.set(id, timeout);
      }
    },
    [defaultDuration, clearAnnouncement]
  );

  // Convenience methods for different announcement types
  const announceSuccess = useCallback(
    (message: string, duration?: number) => {
      announce(message, 'success', 'polite', duration);
    },
    [announce]
  );

  const announceError = useCallback(
    (message: string, duration?: number) => {
      announce(message, 'error', 'assertive', duration);
    },
    [announce]
  );

  const announceInfo = useCallback(
    (message: string, duration?: number) => {
      announce(message, 'info', 'polite', duration);
    },
    [announce]
  );

  const announceWarning = useCallback(
    (message: string, duration?: number) => {
      announce(message, 'warning', 'polite', duration);
    },
    [announce]
  );

  const announceStatus = useCallback(
    (message: string, duration?: number) => {
      announce(message, 'status', 'polite', duration);
    },
    [announce]
  );

  const value: AnnouncementContextValue = {
    announcements,
    announce,
    announceSuccess,
    announceError,
    announceInfo,
    announceWarning,
    announceStatus,
    clearAnnouncement,
    clearAllAnnouncements,
  };

  return <AnnouncementContext.Provider value={value}>{children}</AnnouncementContext.Provider>;
};

export default AnnouncementContext;
