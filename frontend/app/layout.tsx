import type { Metadata } from 'next'
import { Playfair_Display, DM_Sans, JetBrains_Mono } from 'next/font/google'
import './globals.css'

const playfair = Playfair_Display({
  subsets: ['latin'],
  weight: ['700', '900'],
  variable: '--font-display',
  display: 'swap',
})

const dmSans = DM_Sans({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600'],
  variable: '--font-body',
  display: 'swap',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'AKTU PYQ Intelligence — Find What Actually Gets Asked',
  description: 'Semantic search over AKTU previous-year question papers. Find the most repeated questions by subject, unit, and type in seconds.',
  keywords: 'AKTU PYQ, previous year questions, AKTU exam preparation, repeated questions',
  openGraph: {
    title: 'AKTU PYQ Intelligence',
    description: 'Find the most repeated AKTU exam questions instantly.',
    type: 'website',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${playfair.variable} ${dmSans.variable} ${jetbrainsMono.variable}`}>
      <body className="relative">
        <div className="orb w-96 h-96 bg-gold-500/10 top-0 -left-20" />
        <div className="orb w-80 h-80 bg-jade-500/8 top-1/3 right-0" style={{ animationDelay: '-8s' }} />
        <div className="orb w-64 h-64 bg-gold-500/6 bottom-0 left-1/2" style={{ animationDelay: '-14s' }} />
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  )
}
