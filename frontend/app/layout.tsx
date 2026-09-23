import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Career Quest",
  description: "Персональный навигатор карьерного развития",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>
        <header className="topbar">
          <Link href="/" className="brand"><span className="brandMark">CQ</span> Career Quest</Link>
          <nav><Link href="/">Сотрудник</Link><Link href="/hr">HR-аналитика</Link></nav>
        </header>
        {children}
      </body>
    </html>
  );
}
