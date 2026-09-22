/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // 奶油暖白背景（大地有机感）
        cream: {
          50: '#FAF7F2',
          100: '#F5F0E8',
          200: '#EDE6DA',
          300: '#E0D5C8',
        },
        // 深摩卡棕文字（静谧奢华）
        mocha: {
          DEFAULT: '#2A1F1A',
          soft: '#5C4A3E',
          mute: '#8B7565',
          faint: '#B8A494',
        },
        // 主色 - 赤陶橙（低饱和，高级食欲色）
        terracotta: {
          DEFAULT: '#B85C38',
          soft: '#D4845E',
          deep: '#9A4528',
          light: '#F0DDD0',
        },
        // 辅助色 - 苔藓绿（低饱和，自然生长感）
        moss: {
          DEFAULT: '#6B7F5E',
          soft: '#8FA080',
          deep: '#4F6045',
          light: '#E0E5D8',
        },
        // 点缀色 - 芥末金（温暖高级）
        mustard: {
          DEFAULT: '#C9A961',
          soft: '#DCC085',
          deep: '#A88840',
          light: '#F0E8D0',
        },
        // 菜系分类色（低饱和大地色系）
        cuisine: {
          japanese: '#B85C38',   // 赤陶橙 - 日料
          chinese: '#8B5E3C',     // 焦糖棕 - 中餐
          asian: '#6B7F5E',       // 苔藓绿 - 亚洲
          western: '#5C6B7A',     // 灰蓝 - 西餐
          other: '#7A6B5C',       // 灰褐色 - 其他
        },
        // 档位色
        tier: {
          casual: '#6B7F5E',      // 苔藓绿 - 亲民
          mid: '#C9A961',         // 芥末金 - 中端
          premium: '#B85C38',     // 赤陶橙 - 高端
        },
        // 边框线
        line: '#E0D5C8',
      },
      fontFamily: {
        serif: ['"Fraunces"', '"Playfair Display"', '"Noto Serif SC"', 'Georgia', 'serif'],
        sans: ['Inter', '"Noto Sans SC"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Menlo', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '1rem' }],
        'display': ['clamp(3rem, 8vw, 6rem)', { lineHeight: '0.95', letterSpacing: '-0.02em' }],
      },
      letterSpacing: {
        'widest-xl': '0.2em',
      },
      borderRadius: {
        'xl2': '1rem',
        '3xl2': '1.5rem',
      },
      boxShadow: {
        'soft': '0 2px 20px rgba(42,31,26,0.06)',
        'card': '0 4px 30px rgba(42,31,26,0.08)',
        'lift': '0 8px 40px rgba(42,31,26,0.12)',
      },
      maxWidth: {
        'reading': '680px',
      },
    },
  },
  plugins: [],
};
