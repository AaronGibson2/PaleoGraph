import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "PaleoGraph", template: "%s | PaleoGraph" },
  description: "Explore the fossil record through time, place, and scientific sources.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">Skip to content</a>
        <header className="site-header">
          <Link className="wordmark" href="/">PaleoGraph</Link>
          <nav aria-label="Main navigation"><Link href="/explore">Explore</Link></nav>
        </header>
        <main id="main" tabIndex={-1}>{children}</main>
      </body>
    </html>
  );
}
