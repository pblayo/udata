var path = require('path');
var webpack = require('webpack');

var ExtractTextPlugin = require('extract-text-webpack-plugin');
var node_path = path.join(__dirname, 'node_modules');

var vue = require('vue-loader'),
    css_loader = ExtractTextPlugin.extract('style', 'css?sourceMap'),
    less_loader = ExtractTextPlugin.extract('style', 'css?sourceMap!less?sourceMap=source-map-less-inline'),
    html_loader = 'html?collapseBooleanAttributes=false&collapseWhitespace=false"',
    js_loader = 'babel';

var languages = ['en', 'fr'];

module.exports = {
    entry: {
        admin: "./js/main.js",
    },
    output: {
        path: path.join(__dirname, 'udata_admin', 'static'),
        publicPath: "/admin/static/",
        filename: "[name].js",
        chunkFilename: "[id].[hash].js"
    },
    resolve: {
        root: [
            __dirname,
            path.join(__dirname, 'js'),
        ],
        alias: {
            'jquery-slimscroll': path.join(node_path, 'jquery-slimscroll/jquery.slimscroll'),
            'fineuploader': path.join(node_path, 'fine-uploader/fine-uploader/fine-uploader'),
        }
    },
    devtool: 'eval-source-map',
    module: {
        loaders: [
            {test: /\.(jpg|jpeg|png|gif|svg)$/, loader: 'file'},
            {test: /\.css$/, loader: css_loader},
            {test: /\.less$/, loader: less_loader},
            {test: /\.vue$/, loader: vue.withLoaders({
                html: html_loader,
                css: css_loader,
                less: less_loader,
                js: js_loader
            })},
            {test: /\.json$/, loader: "json"},
            {test: /\.html$/, loader: html_loader},
            {test: /\.(woff|svg|ttf|eot|otf)([\?]?.*)$/, loader: "file-loader?name=[name].[ext]"},
            {test: /\.js$/, loader: js_loader,
                include: [
                    path.resolve(__dirname, 'js'),
                    path.resolve(__dirname, 'specs'),
                ],
                exclude: path.resolve(__dirname, 'specs', 'loader.js')
            },
        ]
    },
    plugins: [
        // Fix AdminLTE packaging
        new webpack.NormalModuleReplacementPlugin(
            /admin-lte\/build\/img\/boxed-bg\.jpg$/,
            'admin-lte/dist/img/boxed-bg.jpg'
        ),
        // new webpack.ContextReplacementPlugin(/admin-lte\/build\/img\/.*$/, 'admin-lte/dist/img/$1'),
        new webpack.ProvidePlugin({
            $: 'jquery',
            jQuery: 'jquery',
            'window.jQuery': 'jquery',
        }),
        new ExtractTextPlugin('[name].css'),
        new webpack.IgnorePlugin(/^(\.\/)?shred/),
        new webpack.ContextReplacementPlugin(/moment\/locale$/, new RegExp(languages.join('|')))
    ]
};