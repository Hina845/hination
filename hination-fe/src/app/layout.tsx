import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Điện Biên Forecast",
  description: "Bản đồ dự báo và cảnh báo thiên tai Điện Biên",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body className="min-h-full bg-white font-sans text-[#363636]">{children}</body>
    </html>
  );
}
