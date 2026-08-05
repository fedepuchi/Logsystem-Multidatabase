import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },   // Configuración del entorno de pruebas utilizando Vitest
  build: {
    outDir: "dist",
  },
  test: {
    globals: true, // Permite utilizar funciones globales de Vitest como describe(), test() y expect()
    environment: "jsdom", // Simula un entorno de navegador mediante jsdom para poder probar componentes React
    setupFiles: "./src/setupTests.ts", // Ejecuta este archivo antes de cada prueba para cargar configuraciones adicionales 
  }, 
});
