import type {NextConfig} from 'next';

const securityHeaders = [
  {key: 'Cross-Origin-Opener-Policy', value: 'same-origin'},
  {key: 'Cross-Origin-Resource-Policy', value: 'same-origin'},
  {key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin'},
  {key: 'X-Content-Type-Options', value: 'nosniff'},
  {key: 'X-Frame-Options', value: 'DENY'},
  {key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()'},
];

const nextConfig: NextConfig = {
  allowedDevOrigins: ['127.0.0.1'],
  poweredByHeader: false,
  reactStrictMode: true,
  experimental: {
    serverActions: {
      bodySizeLimit: '256kb',
    },
  },
  async headers() {
    return [{source: '/:path*', headers: securityHeaders}];
  },
};

export default nextConfig;
