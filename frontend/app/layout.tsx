import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "File Vault",
  description: "Private file storage with optional copying to your Google Drive.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
