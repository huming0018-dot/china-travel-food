import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import { supabase } from '@/lib/supabase';

export default function AuthCallback() {
  const router = useRouter();
  const [status, setStatus] = useState<'loading' | 'error'>('loading');
  const [message, setMessage] = useState('正在登录...');

  const redirected = useRef(false);
  const codeRequest = useRef<{ code: string; promise: ReturnType<typeof supabase.auth.exchangeCodeForSession> } | null>(null);

  useEffect(() => {
    if (!router.isReady) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const finish = () => {
      if (!active || redirected.current) return;
      redirected.current = true;
      if (timer !== undefined) clearTimeout(timer);
      void router.replace('/');
    };
    const failed = (message: string) => {
      if (!active || redirected.current) return;
      setStatus('error'); setMessage(message);
    };
    const { code } = router.query;
    if (typeof code === 'string' && code) {
      // Reuse an in-flight redemption if React restarts this effect.
      if (!codeRequest.current || codeRequest.current.code !== code) {
        codeRequest.current = { code, promise: supabase.auth.exchangeCodeForSession(code) };
      }
      codeRequest.current.promise.then(({ error }) => {
        if (error) failed(`登录失败：${error.message}`);
        else finish();
      }).catch(() => failed('登录暂时不可用，请重试。'));
      return () => { active = false; };
    }
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) finish();
    });
    timer = setTimeout(() => failed('未收到有效的登录凭证，请重试。'), 5000);
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) finish();
    }).catch(() => failed('登录暂时不可用，请重试。'));
    return () => {
      active = false;
      subscription.unsubscribe();
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [router.isReady, router.query.code, router]);

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
