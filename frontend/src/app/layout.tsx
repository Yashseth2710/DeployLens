import type { Metadata } from "next";
import { Archivo, Azeret_Mono } from "next/font/google";

import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  display: "swap",
});

const azeret = Azeret_Mono({
  variable: "--font-azeret",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "DeployLens",
  description:
    "Deployment and uptime tracking for the projects you ship to free hosting. Every GitHub Actions run, every deploy, every endpoint, on one sheet.",
};

const DESIGN_NOTE = `<!--
  DeployLens reads as a press check.

  Every deploy is an impression pulled off the press, and the dashboard is the
  sheet you sign off. Panels are bounded by crop marks rather than borders; the
  strip down a panel edge is a colour control bar carrying real deploy history;
  a score is read off a density step wedge. Dark is the pressroom at night under
  one viewing booth; light is the same sheet on the bench under D50. Neither is
  an inversion of the other.

  Rules this build holds itself to: one light source and no floating glow; every
  label at one size, ranked by ink rather than scale; every number states the
  window and the sample it came from; one window control retunes the whole page.
-->`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${archivo.variable} ${azeret.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <div hidden dangerouslySetInnerHTML={{ __html: DESIGN_NOTE }} />
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
