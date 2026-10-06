/** @type {import('next').NextConfig} */
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
  images: {
    domains: ['images.unsplash.com', '*.supabase.co'],
  },
};

module.exports = withPWA(nextConfig);
