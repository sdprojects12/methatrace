import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";
import DashboardShell from "../src/components/DashboardShell";
import { ThemeProvider } from "../src/components/ThemeProvider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "MethaTrace",
  description: "Methane intelligence and pipeline monitoring dashboard",
};

/**
 * Runs before the first paint so the saved (or system) theme is applied
 * without flashing the default dark theme. If nothing is stored, the system
 * light preference is honoured and dark remains the fallback.
 */
const themeScript = `(function(){try{var key="methatrace-theme";var stored=null;try{stored=window.localStorage.getItem(key);}catch(storageError){}var theme=stored==="light"||stored==="dark"?stored:(window.matchMedia&&window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");var root=document.documentElement;root.dataset.theme=theme;root.style.colorScheme=theme;}catch(error){document.documentElement.dataset.theme="dark";}})();`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full flex flex-col bg-background font-sans text-foreground">
        <ThemeProvider>
          <DashboardShell>{children}</DashboardShell>
        </ThemeProvider>
      </body>
    </html>
  );
}
