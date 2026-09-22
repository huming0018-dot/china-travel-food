import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import { supabase } from '@/lib/supabase';

export default function AuthCallback() {
  const router = useRouter();
  const [status, setStatus] = useState<'loading' | 'error'>('loading');
  const [message, setMessage] = useState('正在登录...');

  useEffect(() => {
    // 处理 ?code=xxx 格式的魔法链接回调
    const { code } = router.query;
    if (code && typeof code === 'string') {
      supabase.auth.exchangeCodeForSession(code).then(({ error }) => {
        if (error) {
          setStatus('error');
          setMessage(`登录失败：${error.message}`);
        } else {
          router.replace('/');
        }
      });
    } else {
      // 有些版本会用 #access_token= 格式
      supabase.auth.onAuthStateChange((event, session) => {
        if (session) {
          router.replace('/');
        }
      });
      // 如果没有 code 也没有 session，提示错误
      setTimeout(() => {
        setStatus('error');
        setMessage('未收到有效的登录凭证，请重试。');
      }, 5000);
    }
  }, [router]);

  return (
    <div className="min-h-screen bg-cream-50 flex items-center justify-center px-6">
      <Head><title>登录中 · China Travel</title></Head>
      <div className="text-center">
        {status === 'loading' ? (
          <>
            <div className="spinner mx-auto mb-4" />
            <p className="text-sm text-mocha-faint">{message}</p>
          </>
        ) : (
          <>
            <p className="text-sm text-terracotta-deep mb-4">{message}</p>
            <button
              onClick={() => router.push('/login')}
              className="btn btn-outline"
            >
              返回登录
            </button>
          </>
        )}
      </div>
    </div>
  );
}
