/** @type {import('next').NextConfig} */
// This checked-in configuration contains only the project's public URL and
// publishable key. Preview builds do not receive the ignored local .env file.
const publicSupabase = require('./supabase.public.json');
const withPWA = require('@ducanh2912/next-pwa').default({
  dest: 'public',
  register: true,
  skipWaiting: true,
  cacheOnFrontEndNav: true,
  reloadOnOnline: true,
  disable: process.env.NODE_ENV === 'development',
  extendDefaultRuntimeCaching: true,
  workboxOptions: {
    disableDevLogs: true,
    runtimeCaching: [{urlPattern: ({url}) => url.pathname.startsWith('/api/crowd/') || url.pathname.startsWith('/crowd/releases/'), handler: 'NetworkOnly', options: {cacheName: 'crowd-network-only'}}],
  },
});

const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL || publicSupabase.url,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || publicSupabase.key,
  },
  images: {
    domains: ['images.unsplash.com', '*.supabase.co'],
  },
};

module.exports = withPWA(nextConfig);
