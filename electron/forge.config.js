const { FusesPlugin } = require('@electron-forge/plugin-fuses');
const { FuseV1Options, FuseVersion } = require('@electron/fuses');

module.exports = {
  packagerConfig: {
    asar: {
      unpack: '**/*.{py,html,css,js}'
    },
    icon: './assets/icon',
    ignore: [
      /^\/\.vscode/,
      /^\/node_modules\/(?!.*\.(js|json|node)$)/,
      /^\/\.git/,
      /^\/\.gitignore/,
      /^\/README\.md/,
      /^\/\.env/,
      /^\/data/,
      /^\/metadata-fetch-test/,
      /\.pyc$/,
      /__pycache__/
    ],
    extraResource: [
      './app.py',
      './track.py',
      './templates',
      './static',
      './requirements.txt',
      './python_packages',
      'ws.html',
      'config.js'
    ]
  },
  rebuildConfig: {},
  makers: [
    {
      name: '@electron-forge/maker-squirrel',
      config: {},
    },
    {
      name: '@electron-forge/maker-zip',
      platforms: ['darwin'],
    },
    {
      name: '@electron-forge/maker-deb',
      config: {},
    },
    {
      name: '@electron-forge/maker-rpm',
      config: {},
    },
  ],
  plugins: [
    {
      name: '@electron-forge/plugin-auto-unpack-natives',
      config: {},
    },
    // Fuses are used to enable/disable various Electron functionality
    // at package time, before code signing the application
    new FusesPlugin({
      version: FuseVersion.V1,
      [FuseV1Options.RunAsNode]: false,
      [FuseV1Options.EnableCookieEncryption]: true,
      [FuseV1Options.EnableNodeOptionsEnvironmentVariable]: false,
      [FuseV1Options.EnableNodeCliInspectArguments]: false,
      [FuseV1Options.EnableEmbeddedAsarIntegrityValidation]: true,
      [FuseV1Options.OnlyLoadAppFromAsar]: true,
    }),
  ],
};
