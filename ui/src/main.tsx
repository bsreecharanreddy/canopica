import '@fontsource-variable/inter';
import '@fontsource/courier-prime';
import './index.css';
import './i18n/config';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App.tsx';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
