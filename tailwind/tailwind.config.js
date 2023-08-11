module.exports = {
  content: ["../src/**/*.{pt,html}",],
  theme: {
    fontFamily: {
      'sans': ['ConduitITCStd', 'ui-sans-serif', 'system-ui']
    },
    extend: {},
  },
  plugins: [
    require('@tailwindcss/forms'),
    // ...
  ],
}
