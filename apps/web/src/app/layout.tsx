import type { Metadata } from "next";
import { IBM_Plex_Sans_Arabic, Inter } from "next/font/google";
import { cookies, headers } from "next/headers";
import { ServiceStatus } from "@/components/shell/ServiceStatus";
import { RtlProvider } from "@/components/ui/RtlProvider";
import { LANG_COOKIE, dirOf, resolveLang } from "@/i18n";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], display: "swap", variable: "--font-inter" });
const plexArabic = IBM_Plex_Sans_Arabic({
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-plex-arabic",
});

export const metadata: Metadata = {
  title: "CampusPulse",
  description: "Bilingual campus-request triage",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [jar, hdrs] = await Promise.all([cookies(), headers()]);
  const lang = resolveLang(jar.get(LANG_COOKIE)?.value, hdrs.get("accept-language"));
  return (
    <html lang={lang} dir={dirOf(lang)} className={`${inter.variable} ${plexArabic.variable}`}>
      <body>
        <RtlProvider lang={lang}>
          <ServiceStatus />
          {children}
        </RtlProvider>
      </body>
    </html>
  );
}
