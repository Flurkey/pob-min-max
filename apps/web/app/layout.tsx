import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PoE Forge",
  description: "Phase 1 console for the Path of Building calculation engine.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
