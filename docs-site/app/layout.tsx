import type { Metadata } from 'next';
import { JetBrains_Mono } from 'next/font/google';
import { Provider } from '@/components/provider';
import { appName, appTagline, basePath, siteUrl } from '@/lib/shared';
import './global.css';

// 코드·식별자용. next/font 가 빌드 때 받아 자체 호스팅한다(런타임에 CDN 을 치지 않는다).
const mono = JetBrains_Mono({
  subsets: ['latin'],
  display: 'swap',
  variable: '--hc-font-code',
});

export const metadata: Metadata = {
  title: { default: appName, template: `%s · ${appName}` },
  description: appTagline,
  metadataBase: new URL(siteUrl),
};

export default function Layout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="ko" className={mono.variable} suppressHydrationWarning>
      <head>
        {/* Pretendard Variable — public/fonts 로 베낀 자체 호스팅(scripts/vendor-fonts.mjs).
            basePath 하위로 서빙되므로 경로를 직접 붙인다. */}
        <link
          rel="stylesheet"
          href={`${basePath}/fonts/pretendard/pretendardvariable-dynamic-subset.css`}
        />
      </head>
      <body className="flex min-h-screen flex-col">
        <Provider>{children}</Provider>
      </body>
    </html>
  );
}
