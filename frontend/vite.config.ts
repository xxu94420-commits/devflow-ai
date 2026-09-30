import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()], build:{rollupOptions:{output:{manualChunks:{charts:['echarts'],react:['react','react-dom']}}}}});
