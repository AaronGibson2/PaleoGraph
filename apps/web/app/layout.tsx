import type { Metadata } from "next";
import Link from "next/link";
import { PaleoGraphBrand } from "../features/brand/PaleoGraphBrand";
import "../features/brand/brand.css";
import "./globals.css";
import "./design-tokens.css";

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
          <Link className="wordmark" href="/" aria-label="PaleoGraph home"><PaleoGraphBrand /></Link>
          <nav aria-label="Main navigation"><Link href="/explore">Atlas</Link><Link href="/explore?catalog=open">Catalog</Link><Link href="/lineage">Lineage</Link></nav>
        </header>
        <main id="main" tabIndex={-1}>{children}</main>
      </body>
    </html>
  );
}
