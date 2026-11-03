/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PUBLIC_LANDING?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
