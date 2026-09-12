import type { Metadata, Viewport } from "next";
import "./globals.css";
import SwRegister from "@/components/SwRegister";

export const metadata: Metadata = {
  title: "ORCA — Marine Intelligence",
  description: "Marine EcOsystem Reasoning with Collaborative Agents — SIH 2026 PS 176",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: "#070D1A",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased bg-[#070D1A] text-[#DBE4F3]">
        <SwRegister />
        {children}
      </body>
    </html>
  );
}
