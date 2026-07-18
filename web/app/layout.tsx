import type { Metadata, Viewport } from "next";
import { Fraunces, Inter } from "next/font/google";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";
import "./globals.css";

// Self-hosted via next/font: zero layout shift, no third-party requests.
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-display",
  axes: ["opsz"],
});

const SITE_URL = "https://nepal-data-base-project-7oru.vercel.app";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Nepal Data Portal — trustworthy data about Nepal",
    template: "%s · Nepal Data Portal",
  },
  description:
    "Free, open, verifiable statistics about Nepal's economy, banking system, and society — every figure traceable to its official source.",
  openGraph: {
    title: "Nepal Data Portal",
    description:
      "Nepal's numbers, in one trustworthy place. Open data with the source behind every figure.",
    url: SITE_URL,
    siteName: "Nepal Data Portal",
    locale: "en_US",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#f7f6f2",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${fraunces.variable}`}>
      <body>
        <SiteHeader />
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
