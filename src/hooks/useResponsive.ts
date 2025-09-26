import { useCallback, useEffect, useMemo, useState } from 'react';

/**
 * Breakpoint thresholds matching common responsive design patterns
 */
export const BREAKPOINTS = {
  mobile: 768,
  tablet: 1024,
  desktop: 1280,
  wide: 1536,
} as const;

/**
 * Type for breakpoint names
 */
export type BreakpointName = keyof typeof BREAKPOINTS;

/**
 * Interface for the responsive hook return value
 */
export interface UseResponsiveReturn {
  /** Current window width */
  width: number;
  /** Current window height */
  height: number;
  /** True if screen width is less than mobile breakpoint (768px) */
  isMobile: boolean;
  /** True if screen width is between mobile and tablet breakpoints (768px - 1024px) */
  isTablet: boolean;
  /** True if screen width is between tablet and desktop breakpoints (1024px - 1280px) */
  isDesktop: boolean;
  /** True if screen width is greater than desktop breakpoint (1280px) */
  isWide: boolean;
  isBelow: (breakpoint: BreakpointName | number) => boolean;
  isAbove: (breakpoint: BreakpointName | number) => boolean;
  isBetween: (min: BreakpointName | number, max: BreakpointName | number) => boolean;
  breakpoint: BreakpointName;
}

export function useResponsive(): UseResponsiveReturn {
  // Track current window dimensions
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  // Handler to update dimensions
  const handleResize = useCallback(() => {
    setDimensions({ width: window.innerWidth, height: window.innerHeight });
  }, []);

  useEffect(() => {
    handleResize(); // Set initial size
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [handleResize]);

  // Helper to normalize breakpoint values
  const getBreakpointValue = useCallback((breakpoint: BreakpointName | number) => {
    if (typeof breakpoint === 'number') {
      return breakpoint;
    }
    return BREAKPOINTS[breakpoint];
  }, []);

  // Breakpoint check utilities
  const isBelow = useCallback(
    (breakpoint: BreakpointName | number): boolean => {
      return dimensions.width < getBreakpointValue(breakpoint);
    },
    [dimensions.width, getBreakpointValue]
  );

  const isAbove = useCallback(
    (breakpoint: BreakpointName | number): boolean => {
      return dimensions.width >= getBreakpointValue(breakpoint);
    },
    [dimensions.width, getBreakpointValue]
  );

  const isBetween = useCallback(
    (min: BreakpointName | number, max: BreakpointName | number): boolean => {
      const minValue = getBreakpointValue(min);
      const maxValue = getBreakpointValue(max);
      return dimensions.width >= minValue && dimensions.width < maxValue;
    },
    [dimensions.width, getBreakpointValue]
  );

  // Calculate current breakpoint
  const breakpoint = useMemo((): 'mobile' | 'tablet' | 'desktop' | 'wide' => {
    if (dimensions.width < BREAKPOINTS.mobile) {
      return 'mobile';
    }
    if (dimensions.width < BREAKPOINTS.tablet) {
      return 'tablet';
    }
    if (dimensions.width < BREAKPOINTS.desktop) {
      return 'desktop';
    }
    return 'wide';
  }, [dimensions.width]);

  // Calculate boolean flags for common breakpoints
  const isMobile = useMemo(() => dimensions.width < BREAKPOINTS.mobile, [dimensions.width]);
  const isTablet = useMemo(
    () => dimensions.width >= BREAKPOINTS.mobile && dimensions.width < BREAKPOINTS.tablet,
    [dimensions.width]
  );
  const isDesktop = useMemo(
    () => dimensions.width >= BREAKPOINTS.tablet && dimensions.width < BREAKPOINTS.desktop,
    [dimensions.width]
  );
  const isWide = useMemo(() => dimensions.width >= BREAKPOINTS.desktop, [dimensions.width]);

  return {
    width: dimensions.width,
    height: dimensions.height,
    isMobile,
    isTablet,
    isDesktop,
    isWide,
    isBelow,
    isAbove,
    isBetween,
    breakpoint,
  };
}

/**
 * Re-export for convenience
 */
export default useResponsive;
