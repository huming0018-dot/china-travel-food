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
    runtimeCaching: [{urlPattern: ({url}) => url.pathname === '/materials' || url.pathname.startsWith('/api/publications') || url.pathname.startsWith('/api/crowd/') || url.pathname.startsWith('/crowd/releases/') || (url.protocol === 'https:' && url.host === 'bdwrhshgdeghgyzwpxnl.supabase.co' && url.pathname.startsWith('/storage/v1/object/sign/crowd-publication-snapshots/')), handler: 'NetworkOnly', options: {cacheName: 'crowd-network-only'}}],
  },
});

// 本项目 Supabase 实例域（用于 images.domains 与精确白名单，不再用 *.supabase.co 通配）
const supabaseHost = publicSupabase.url.replace(/^https?:\/\//, '').replace(/\/$/, '');

const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL || publicSupabase.url,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || publicSupabase.key,
  },
  images: {
    // 收紧：仅允许本项目 storage 域与图床，不用 *.supabase.co 通配
    domains: ['images.unsplash.com', supabaseHost],
  },
  async headers() {
    return [
      {source: '/materials', headers: [{key: 'Cache-Control', value: 'private, no-store, max-age=0'}]},
      {
        source: '/:path*',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "img-src 'self' data: blob: https://images.unsplash.com https://*.supabase.co https://*.autonavi.com https://*.amap.com",
              "font-src 'self' data: https://fonts.gstatic.com",
              "connect-src 'self' https://*.supabase.co wss://*.supabase.co https://fonts.googleapis.com https://fonts.gstatic.com",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
            ].join('; '),
          },
          { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'no-referrer' },
        ],
      },
    ];
  },
};

module.exports = withPWA(nextConfig);
