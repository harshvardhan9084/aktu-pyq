'use client'
import { useEffect } from 'react'
import { usePathname } from 'next/navigation'
import {
  trackPageView,
  trackPageExit,
  initScrollTracking,
  startHeartbeat,
  stopHeartbeat,
} from '@/lib/analytics'

export default function AnalyticsInit() {
  const pathname = usePathname()

  useEffect(() => {
    trackPageView()
    const cleanupScroll = initScrollTracking()
    startHeartbeat()

    const handleExit = () => trackPageExit()
    window.addEventListener('beforeunload', handleExit)

    return () => {
      cleanupScroll?.()
      stopHeartbeat()
      window.removeEventListener('beforeunload', handleExit)
    }
  }, [pathname])

  return null
}
