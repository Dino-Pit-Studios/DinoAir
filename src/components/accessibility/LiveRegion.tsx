import { useEffect, useState, type FC } from 'react';

import { useAnnouncement } from '../../hooks/useAnnouncement';

import type { Announcement, AnnouncementPoliteness } from '../../hooks/useAnnouncement';

interface LiveRegionProps {
  /**
   * Filter announcements by politeness level
   * If not specified, will show all announcements
   */
  politeness?: AnnouncementPoliteness | AnnouncementPoliteness[];
  /**
   * Additional CSS classes for the live region container
   */
  className?: string;
  /**
   * Whether to show only the latest announcement
   * @default true
   */
  showLatestOnly?: boolean;
  /**
   * Custom aria-label for the live region
   */
  ariaLabel?: string;
}

/**
 * LiveRegion component that renders aria-live regions for screen reader announcements
 * This component is visually hidden but accessible to assistive technologies
 */
export const LiveRegion: FC<LiveRegionProps> = ({
  politeness,
  className = '',
  showLatestOnly = true,
  ariaLabel = 'Screen reader announcements',
}) => {
  const { announcements } = useAnnouncement();
  const [displayedAnnouncements, setDisplayedAnnouncements] = useState<Announcement[]>([]);

  useEffect(() => {
    // Filter announcements based on politeness level if specified
    let filtered = announcements;

    if (politeness) {
      const politenessLevels = Array.isArray(politeness) ? politeness : [politeness];
      filtered = announcements.filter(a => politenessLevels.includes(a.politeness));
    }

    // Show only the latest announcement if specified
    if (showLatestOnly && filtered.length > 0) {
      setDisplayedAnnouncements([filtered[filtered.length - 1]]);
    } else {
      setDisplayedAnnouncements(filtered);
    }
  }, [announcements, politeness, showLatestOnly]);

  // Group announcements by politeness level
  const groupedAnnouncements = displayedAnnouncements.reduce(
    (acc, announcement) => {
      if (!acc[announcement.politeness]) {
        acc[announcement.politeness] = [];
      }
      acc[announcement.politeness].push(announcement);
      return acc;
    },
    {} as Record<AnnouncementPoliteness, Announcement[]>
  );

  return (
    <>
      {/* Render separate live regions for different politeness levels */}
      {Object.entries(groupedAnnouncements).map(([level, levelAnnouncements]) => {
        const isAssertive = level === 'assertive';
        const Tag = isAssertive ? 'div' : 'output'; // output has implicit role="status"
        return (
          <Tag
            key={level}
            className={`sr-only ${className}`}
            {...(isAssertive ? { role: 'alert' } : {})}
            aria-live={level as AnnouncementPoliteness}
            aria-atomic='true'
            aria-relevant='additions text'
            aria-label={ariaLabel}
          >
            {levelAnnouncements.map(announcement => (
              <div key={announcement.id} data-announcement-type={announcement.type}>
                {announcement.message}
              </div>
            ))}
          </Tag>
        );
      })}

      {/* Always render at least one live region even if empty for consistency */}
      {Object.keys(groupedAnnouncements).length === 0 && (
        <output
          className={`sr-only ${className}`}
          aria-live='polite'
          aria-atomic='true'
          aria-relevant='additions text'
          aria-label={ariaLabel}
        />
      )}
    </>
  );
};

// Export a convenience component for assertive announcements (errors, critical alerts)
export const AssertiveLiveRegion: FC<Omit<LiveRegionProps, 'politeness'>> = props => (
  <LiveRegion {...props} politeness='assertive' />
);

// Export a convenience component for polite announcements (status updates, info)
export const PoliteLiveRegion: FC<Omit<LiveRegionProps, 'politeness'>> = props => (
  <LiveRegion {...props} politeness='polite' />
);
