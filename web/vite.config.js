import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Static build is copied into game/renpy_inspector_web by release CI.
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: { outDir: 'dist', sourcemap: false, emptyOutDir: true },
});
