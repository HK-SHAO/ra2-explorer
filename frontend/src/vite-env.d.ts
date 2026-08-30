/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_RA2EXP_BUILD_COMMIT?: string;
  readonly VITE_RA2EXP_BUILD_TAG?: string;
  readonly VITE_RA2EXP_BUILD_TIME?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
