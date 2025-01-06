module.exports = {
  content: ["../src/**/*.{pt,py,html}",],
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
