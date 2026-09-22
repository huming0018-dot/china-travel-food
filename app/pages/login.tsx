import Head from 'next/head';
import Link from 'next/link';
import { useState } from 'react';
import { useAuth } from '@/lib/auth';
import { useRouter } from 'next/router';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const { signInWithOtp, user } = useAuth();
  const router = useRouter();

  // 已登录则跳转
  if (user) {
    router.replace('/');
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    const result = await signInWithOtp(email);
    setSubmitting(false);
    if (result.error) {
      setError(result.error);
    } else {
      setSent(true);
    }
  };

  return (
    <div className="min-h-screen bg-paper-100 flex items-center justify-center px-6">
      <Head>
        <title>登录 · China Travel</title>
      </Head>

      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-10">
          <Link href="/" className="inline-block">
            <span className="serif text-2xl font-semibold tracking-tight">China Travel</span>
            <div className="kicker text-ink-faint mt-1">FOOD GUIDE · SHANGHAI</div>
          </Link>
        </div>

        {/* 表单卡片 */}
        <div className="border hairline bg-white p-8">
          <div className="flex items-center gap-3 mb-6">
            <span className="w-6 h-px bg-ink" />
            <h1 className="serif text-xl font-medium">欢迎回来</h1>
          </div>

          {error && (
            <div className="mb-5 p-3 border border-signal-deep/30 bg-signal-soft/30 text-signal-deep text-xs">
              ⚠️ {error}
            </div>
          )}

          {sent ? (
            <div className="text-center py-4">
              <div className="text-4xl mb-4">✉️</div>
              <p className="serif text-base mb-2">魔法链接已发送</p>
              <p className="text-sm text-ink-faint leading-relaxed">
                请查收 <span className="font-medium text-ink">{email}</span> 的邮件，
                点击邮件中的链接即可登录。
              </p>
              <p className="text-2xs text-ink-faint mt-4">
                邮件可能在垃圾邮件文件夹中，链接 60 分钟内有效。
              </p>
              <button
                onClick={() => setSent(false)}
                className="mt-6 text-2xs text-terracotta underline"
              >
                重新输入邮箱
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="kicker text-ink-faint block mb-2">邮箱 / EMAIL</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full px-0 py-2.5 bg-transparent border-b hairline text-sm focus:outline-none focus:border-ink transition placeholder:text-ink-faint"
                  placeholder="you@example.com"
                />
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="btn btn-primary w-full mt-4"
              >
                {submitting ? '发送中...' : '发送魔法链接'}
              </button>

              <p className="text-2xs text-ink-faint text-center pt-2">
                无需密码，点击邮件链接即可登录
              </p>
            </form>
          )}
        </div>

        <p className="text-center text-2xs text-ink-faint mt-6">
          登录后可收藏餐厅、发布食客评价
        </p>
      </div>
    </div>
  );
}
