import type { Metadata } from "next";
import "./globals.css";
import "./theme.css";
import "./gamification.css";

export const metadata: Metadata = {
  title: "Career Quest",
  description: "Персональный навигатор карьерного развития",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>
        {children}
      </body>
    </html>
  );
}
