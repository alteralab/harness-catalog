'use client';
import {
  SearchDialog,
  SearchDialogClose,
  SearchDialogContent,
  SearchDialogHeader,
  SearchDialogIcon,
  SearchDialogInput,
  SearchDialogList,
  SearchDialogOverlay,
  type SharedProps,
} from 'fumadocs-ui/components/dialog/search';
import { useStaticSearch } from 'fumadocs-core/search/client';
import { basePath, staticSearchParams } from '@/lib/shared';

export default function HcSearchDialog(props: SharedProps) {
  const search = useStaticSearch({
    // fumadocs 의 기본값은 `/api/search` 다 — basePath 를 모른다(fumadocs-core 는 Vite 의
    // import.meta.env.BASE_URL 로만 본다). 하위 경로 설치에서는 여기서 붙여야 404 가 아니다(실측).
    from: `${basePath}/api/search`,
    search: staticSearchParams,
  });

  return (
    <SearchDialog {...search} {...props}>
      <SearchDialogOverlay />
      <SearchDialogContent>
        <SearchDialogHeader>
          <SearchDialogIcon />
          <SearchDialogInput placeholder="검색 — 스킬 이름·설정값·절차" />
          <SearchDialogClose />
        </SearchDialogHeader>
        <SearchDialogList />
      </SearchDialogContent>
    </SearchDialog>
  );
}
