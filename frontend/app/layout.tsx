import type { Metadata } from "next";
import { Chakra_Petch, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import TopNav from "@/components/SidebarNav";

const display = Chakra_Petch({
  weight: "600",
  subsets: ["latin"],
  variable: "--font-chakra",
});

const body = IBM_Plex_Sans({
  weight: ["400", "500"],
  subsets: ["latin"],
  variable: "--font-plex",
});

const mono = IBM_Plex_Mono({
  weight: "500",
  subsets: ["latin"],
  variable: "--font-plex-mono",
});

export const metadata: Metadata = {
  title: "CAGE",
  description: "Construction site safety intelligence",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${display.variable} ${body.variable} ${mono.variable}`}>
        <div className="app-shell">
          <header className="topbar">
            <div className="topbar-inner">
              <div className="brand">
                <span className="brand-mark" aria-hidden>
                  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                    <rect x="2" y="2" width="14" height="14" stroke="currentColor" strokeWidth="1.8" />
                    <path d="M6.5 2v14M11.5 2v14" stroke="currentColor" strokeWidth="1.8" />
                  </svg>
                </span>
                <span className="brand-name">CAGE</span>
              </div>
              <TopNav />
            </div>
          </header>

          <main className="main-content">{children}</main>

          <footer className="colophon">
            <div className="colophon-inner">
              <span>CAGE site safety console</span>
              <span className="colophon-rule" aria-hidden />
              <span>Yolo, Sam 3.1, Muse spark</span>
              <span className="colophon-rule" aria-hidden />
              <span>Sheet v0.3</span>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
