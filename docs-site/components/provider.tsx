'use client';
import HcSearchDialog from '@/components/search';
import { RootProvider } from 'fumadocs-ui/provider/next';
import type { ReactNode } from 'react';

// 문서가 전부 한국어다 — UI 글자도 한국어로 둔다(로케일은 하나뿐이므로 언어 전환기는 없다).
const translations: Record<string, string> = {
  'Search(search dialog)': '검색',
  'Search(search trigger)': '검색',
  'Open Search(search trigger)(aria-label)': '검색 열기',
  'Close Search(search dialog)(aria-label)': '검색 닫기',
  'No results found(search dialog)': '찾은 것이 없습니다',
  'Search failed(search dialog)': '검색이 실패했습니다',
  'On this page(table of contents)': '이 쪽의 목차',
  'No Headings(table of contents)': '제목이 없습니다',
  'Table of Contents(inline table of contents)': '목차',
  'Next Page(pagination)': '다음',
  'Previous Page(pagination)': '이전',
  'Edit on GitHub(edit page)': 'GitHub 에서 고치기',
  'Last updated on(page footer)': '마지막 갱신',
  'Copy Text(code block)(aria-label)': '복사',
  'Copied Text(code block)(aria-label)': '복사했습니다',
  'Copy Markdown(page actions)': '마크다운 복사',
  'Copied Markdown(page actions)': '복사했습니다',
  'Copy Anchor Link(heading anchor)(aria-label)': '이 절의 링크 복사',
  'Copied Anchor Link(heading anchor)(aria-label)': '복사했습니다',
  'Open(page actions)': '열기',
  'Open in GitHub(page actions)': 'GitHub 에서 보기',
  'Theme(site menu)': '테마',
  'Light(theme switcher)(aria-label)': '밝게',
  'Dark(theme switcher)(aria-label)': '어둡게',
  'System(theme switcher)(aria-label)': '시스템',
  'Open Sidebar(aria-label)': '목차 열기',
  'Close Sidebar(aria-label)': '목차 닫기',
  'Open Sidebar(sidebar)(aria-label)': '목차 열기',
  'Close Sidebar(sidebar)(aria-label)': '목차 닫기',
  'Collapse Sidebar(sidebar)(aria-label)': '목차 접기',
  'Hide Sidebar(sidebar)': '목차 감추기',
  'Show Sidebar(sidebar)': '목차 보이기',
  'Page Not Found(404 not found page)': '없는 쪽입니다',
  'Back to Home(404 not found page)': '첫 쪽으로',
  'Options(aria-label)': '더 보기',
};

export function Provider({ children }: { children: ReactNode }) {
  return (
    <RootProvider
      search={{ SearchDialog: HcSearchDialog }}
      i18n={{ locale: 'ko', translations }}
      theme={{ defaultTheme: 'system' }}
    >
      {children}
    </RootProvider>
  );
}
