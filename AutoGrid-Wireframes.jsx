import React, { useState } from 'react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { Play, Pause, Settings, TrendingUp, TrendingDown, Bot, Zap, Shield, Clock, DollarSign, ChevronRight, Bell, User, Menu, Home, PieChart, History, MessageCircle, CreditCard, ArrowUpRight, ArrowDownRight, Activity, Target, Layers, Send, Check, X, RefreshCw, BarChart2, GitBranch, Globe, Lock, Smartphone, Github } from 'lucide-react';

// Mock data
const portfolioData = [
  { date: 'Jan', value: 10000 },
  { date: 'Feb', value: 10800 },
  { date: 'Mar', value: 10200 },
  { date: 'Apr', value: 11500 },
  { date: 'May', value: 12800 },
  { date: 'Jun', value: 14200 },
];

const backtestData = [
  { date: '01', portfolio: 10000, benchmark: 10000 },
  { date: '05', portfolio: 10200, benchmark: 10050 },
  { date: '10', portfolio: 10800, benchmark: 10100 },
  { date: '15', portfolio: 10400, benchmark: 9800 },
  { date: '20', portfolio: 11200, benchmark: 9900 },
  { date: '25', portfolio: 11800, benchmark: 10200 },
  { date: '30', portfolio: 12400, benchmark: 10300 },
];

const tradesData = [
  { time: '14:32', pair: 'BTC/USDT', type: 'BUY', amount: '0.015', price: '43,250', pnl: '+2.4%' },
  { time: '14:28', pair: 'ETH/USDT', type: 'SELL', amount: '0.85', price: '2,280', pnl: '+1.8%' },
  { time: '14:15', pair: 'BTC/USDT', type: 'BUY', amount: '0.012', price: '43,180', pnl: '+0.6%' },
  { time: '13:58', pair: 'SOL/USDT', type: 'SELL', amount: '12.5', price: '98.40', pnl: '-0.3%' },
];

// Sidebar Component
const Sidebar = ({ activeScreen, setActiveScreen }) => {
  const menuItems = [
    { id: 'dashboard', icon: Home, label: 'Dashboard' },
    { id: 'bots', icon: Bot, label: 'My Bots' },
    { id: 'backtest', icon: BarChart2, label: 'Backtesting' },
    { id: 'telegram', icon: MessageCircle, label: 'Telegram Bot' },
    { id: 'pricing', icon: CreditCard, label: 'Pricing' },
  ];

  return (
    <div className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-teal-400 to-cyan-500 rounded-xl flex items-center justify-center">
            <Layers className="w-6 h-6 text-slate-900" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">AutoGrid</h1>
            <p className="text-xs text-slate-500">v1.0 Beta</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4">
        <ul className="space-y-1">
          {menuItems.map((item) => (
            <li key={item.id}>
              <button
                onClick={() => setActiveScreen(item.id)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 ${
                  activeScreen === item.id
                    ? 'bg-teal-500/10 text-teal-400 border border-teal-500/20'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                }`}
              >
                <item.icon className="w-5 h-5" />
                <span className="font-medium">{item.label}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* Open Source Badge */}
      <div className="px-4 pb-2">
        <a href="#" className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800/50 text-slate-400 hover:text-white transition">
          <Github className="w-4 h-4" />
          <span className="text-sm">Open Source</span>
          <span className="ml-auto text-xs bg-teal-500/20 text-teal-400 px-2 py-0.5 rounded-full">MIT</span>
        </a>
      </div>

      {/* User */}
      <div className="p-4 border-t border-slate-800">
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-800/50">
          <div className="w-10 h-10 bg-gradient-to-br from-violet-500 to-fuchsia-500 rounded-full flex items-center justify-center">
            <span className="text-white font-bold">A</span>
          </div>
          <div className="flex-1">
            <p className="text-white font-medium text-sm">Alex</p>
            <p className="text-xs text-teal-400">Pro Cloud</p>
          </div>
          <Settings className="w-5 h-5 text-slate-500" />
        </div>
      </div>
    </div>
  );
};

// Dashboard Screen
const DashboardScreen = () => {
  return (
    <div className="flex-1 bg-slate-950 overflow-auto">
      {/* Header */}
      <header className="border-b border-slate-800 px-8 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white">Dashboard</h2>
            <p className="text-slate-500 text-sm">Overview of your portfolio performance</p>
          </div>
          <div className="flex items-center gap-4">
            <button className="p-2 rounded-lg bg-slate-800 text-slate-400 hover:text-white transition">
              <Bell className="w-5 h-5" />
            </button>
            <button className="px-4 py-2 bg-teal-500 text-slate-900 font-semibold rounded-lg hover:bg-teal-400 transition flex items-center gap-2">
              <Bot className="w-4 h-4" />
              New Bot
            </button>
          </div>
        </div>
      </header>

      <div className="p-8">
        {/* Stats Cards */}
        <div className="grid grid-cols-4 gap-6 mb-8">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-slate-500 text-sm">Total Balance</span>
              <div className="w-10 h-10 bg-teal-500/10 rounded-xl flex items-center justify-center">
                <DollarSign className="w-5 h-5 text-teal-400" />
              </div>
            </div>
            <p className="text-3xl font-bold text-white">$14,280</p>
            <div className="flex items-center gap-2 mt-2">
              <ArrowUpRight className="w-4 h-4 text-teal-400" />
              <span className="text-teal-400 text-sm font-medium">+42.8%</span>
              <span className="text-slate-500 text-sm">this month</span>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-slate-500 text-sm">Today's Profit</span>
              <div className="w-10 h-10 bg-cyan-500/10 rounded-xl flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-cyan-400" />
              </div>
            </div>
            <p className="text-3xl font-bold text-white">$342</p>
            <div className="flex items-center gap-2 mt-2">
              <ArrowUpRight className="w-4 h-4 text-teal-400" />
              <span className="text-teal-400 text-sm font-medium">+2.4%</span>
              <span className="text-slate-500 text-sm">vs yesterday</span>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-slate-500 text-sm">Active Bots</span>
              <div className="w-10 h-10 bg-violet-500/10 rounded-xl flex items-center justify-center">
                <Bot className="w-5 h-5 text-violet-400" />
              </div>
            </div>
            <p className="text-3xl font-bold text-white">4</p>
            <div className="flex items-center gap-2 mt-2">
              <Activity className="w-4 h-4 text-violet-400" />
              <span className="text-slate-400 text-sm">3 Grid, 1 DCA</span>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-slate-500 text-sm">Win Rate</span>
              <div className="w-10 h-10 bg-amber-500/10 rounded-xl flex items-center justify-center">
                <Target className="w-5 h-5 text-amber-400" />
              </div>
            </div>
            <p className="text-3xl font-bold text-white">68.5%</p>
            <div className="flex items-center gap-2 mt-2">
              <span className="text-slate-400 text-sm">142 trades this month</span>
            </div>
          </div>
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-3 gap-6 mb-8">
          {/* Portfolio Chart */}
          <div className="col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-white">Portfolio Performance</h3>
              <div className="flex gap-2">
                {['7D', '1M', '3M', '1Y'].map((period, i) => (
                  <button
                    key={period}
                    className={`px-3 py-1 rounded-lg text-sm font-medium transition ${
                      i === 1 ? 'bg-teal-500/10 text-teal-400' : 'text-slate-500 hover:text-white'
                    }`}
                  >
                    {period}
                  </button>
                ))}
              </div>
            </div>
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={portfolioData}>
                <defs>
                  <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#14b8a6" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#14b8a6" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={12} />
                <YAxis stroke="#64748b" fontSize={12} />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#0f172a', 
                    border: '1px solid #1e293b',
                    borderRadius: '12px',
                    color: '#fff'
                  }} 
                />
                <Area type="monotone" dataKey="value" stroke="#14b8a6" strokeWidth={2} fill="url(#colorValue)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Active Bots */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Active Bots</h3>
            <div className="space-y-4">
              {[
                { name: 'Grid BTC/USDT', profit: '+12.4%', status: 'running' },
                { name: 'DCA ETH', profit: '+8.2%', status: 'running' },
                { name: 'Grid SOL/USDT', profit: '+5.1%', status: 'running' },
                { name: 'Grid MATIC', profit: '-1.2%', status: 'paused' },
              ].map((bot, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-slate-800/50 rounded-xl">
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${bot.status === 'running' ? 'bg-teal-400 animate-pulse' : 'bg-slate-500'}`} />
                    <span className="text-white font-medium text-sm">{bot.name}</span>
                  </div>
                  <span className={`font-mono text-sm ${bot.profit.startsWith('+') ? 'text-teal-400' : 'text-red-400'}`}>
                    {bot.profit}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Recent Trades */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-white">Recent Trades</h3>
            <button className="text-teal-400 text-sm font-medium hover:underline">View all</button>
          </div>
          <table className="w-full">
            <thead>
              <tr className="text-slate-500 text-sm">
                <th className="text-left pb-4">Time</th>
                <th className="text-left pb-4">Pair</th>
                <th className="text-left pb-4">Type</th>
                <th className="text-right pb-4">Amount</th>
                <th className="text-right pb-4">Price</th>
                <th className="text-right pb-4">P&L</th>
              </tr>
            </thead>
            <tbody>
              {tradesData.map((trade, i) => (
                <tr key={i} className="border-t border-slate-800">
                  <td className="py-4 text-slate-400 font-mono text-sm">{trade.time}</td>
                  <td className="py-4 text-white font-medium">{trade.pair}</td>
                  <td className="py-4">
                    <span className={`px-2 py-1 rounded-lg text-xs font-semibold ${
                      trade.type === 'BUY' ? 'bg-teal-500/10 text-teal-400' : 'bg-red-500/10 text-red-400'
                    }`}>
                      {trade.type}
                    </span>
                  </td>
                  <td className="py-4 text-right text-slate-300 font-mono">{trade.amount}</td>
                  <td className="py-4 text-right text-slate-300 font-mono">${trade.price}</td>
                  <td className={`py-4 text-right font-mono font-semibold ${
                    trade.pnl.startsWith('+') ? 'text-teal-400' : 'text-red-400'
                  }`}>
                    {trade.pnl}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

// Bot Configuration Screen
const BotsScreen = () => {
  const [botType, setBotType] = useState('grid');
  
  return (
    <div className="flex-1 bg-slate-950 overflow-auto">
      <header className="border-b border-slate-800 px-8 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white">Configure Bot</h2>
            <p className="text-slate-500 text-sm">Create or edit your automated strategies</p>
          </div>
        </div>
      </header>

      <div className="p-8">
        <div className="grid grid-cols-3 gap-8">
          {/* Bot Type Selection */}
          <div className="col-span-1">
            <h3 className="text-white font-semibold mb-4">Bot Type</h3>
            <div className="space-y-3">
              <button
                onClick={() => setBotType('grid')}
                className={`w-full p-4 rounded-xl border transition-all ${
                  botType === 'grid'
                    ? 'bg-teal-500/10 border-teal-500/30 text-white'
                    : 'bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                    botType === 'grid' ? 'bg-teal-500/20' : 'bg-slate-800'
                  }`}>
                    <Layers className={`w-6 h-6 ${botType === 'grid' ? 'text-teal-400' : 'text-slate-500'}`} />
                  </div>
                  <div className="text-left">
                    <p className="font-semibold">Grid Bot</p>
                    <p className="text-xs text-slate-500">Buy/sell at price ranges</p>
                  </div>
                </div>
              </button>

              <button
                onClick={() => setBotType('dca')}
                className={`w-full p-4 rounded-xl border transition-all ${
                  botType === 'dca'
                    ? 'bg-cyan-500/10 border-cyan-500/30 text-white'
                    : 'bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                    botType === 'dca' ? 'bg-cyan-500/20' : 'bg-slate-800'
                  }`}>
                    <RefreshCw className={`w-6 h-6 ${botType === 'dca' ? 'text-cyan-400' : 'text-slate-500'}`} />
                  </div>
                  <div className="text-left">
                    <p className="font-semibold">DCA Bot</p>
                    <p className="text-xs text-slate-500">Dollar Cost Averaging</p>
                  </div>
                </div>
              </button>
            </div>

            {/* Exchange Selection */}
            <h3 className="text-white font-semibold mt-8 mb-4">Exchange</h3>
            <div className="grid grid-cols-2 gap-3">
              {['Binance', 'MEXC', 'Bybit', 'KuCoin'].map((ex, i) => (
                <button
                  key={ex}
                  className={`p-3 rounded-xl border transition-all text-sm font-medium ${
                    i === 0
                      ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                      : 'bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700'
                  }`}
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>

          {/* Configuration Form */}
          <div className="col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h3 className="text-white font-semibold mb-6">Grid Bot Parameters</h3>
            
            <div className="grid grid-cols-2 gap-6">
              {/* Pair */}
              <div>
                <label className="block text-slate-400 text-sm mb-2">Trading Pair</label>
                <select className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-teal-500">
                  <option>BTC/USDT</option>
                  <option>ETH/USDT</option>
                  <option>SOL/USDT</option>
                  <option>MATIC/USDT</option>
                </select>
              </div>

              {/* Investment */}
              <div>
                <label className="block text-slate-400 text-sm mb-2">Total Investment</label>
                <div className="relative">
                  <input
                    type="text"
                    defaultValue="1000"
                    className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-teal-500"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500">USDT</span>
                </div>
              </div>

              {/* Price Range */}
              <div>
                <label className="block text-slate-400 text-sm mb-2">Lower Price</label>
                <div className="relative">
                  <input
                    type="text"
                    defaultValue="40000"
                    className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-teal-500"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500">$</span>
                </div>
              </div>

              <div>
                <label className="block text-slate-400 text-sm mb-2">Upper Price</label>
                <div className="relative">
                  <input
                    type="text"
                    defaultValue="48000"
                    className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-teal-500"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500">$</span>
                </div>
              </div>

              {/* Grid Lines */}
              <div>
                <label className="block text-slate-400 text-sm mb-2">Number of Grids</label>
                <input
                  type="range"
                  min="5"
                  max="50"
                  defaultValue="20"
                  className="w-full accent-teal-500"
                />
                <div className="flex justify-between text-xs text-slate-500 mt-1">
                  <span>5</span>
                  <span className="text-teal-400 font-semibold">20</span>
                  <span>50</span>
                </div>
              </div>

              {/* Take Profit */}
              <div>
                <label className="block text-slate-400 text-sm mb-2">Take Profit (%)</label>
                <input
                  type="text"
                  defaultValue="25"
                  className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-teal-500"
                />
              </div>
            </div>

            {/* Preview */}
            <div className="mt-8 p-4 bg-slate-800/50 rounded-xl border border-slate-700">
              <h4 className="text-slate-400 text-sm mb-3">Strategy Preview</h4>
              <div className="grid grid-cols-4 gap-4 text-center">
                <div>
                  <p className="text-2xl font-bold text-white">20</p>
                  <p className="text-xs text-slate-500">Orders</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-white">$50</p>
                  <p className="text-xs text-slate-500">Per Grid</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-teal-400">0.42%</p>
                  <p className="text-xs text-slate-500">Profit/Grid</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-cyan-400">~15%</p>
                  <p className="text-xs text-slate-500">Est. APR</p>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-4 mt-8">
              <button className="flex-1 py-3 bg-slate-800 text-white font-semibold rounded-xl hover:bg-slate-700 transition flex items-center justify-center gap-2">
                <BarChart2 className="w-5 h-5" />
                Run Backtest
              </button>
              <button className="flex-1 py-3 bg-teal-500 text-slate-900 font-semibold rounded-xl hover:bg-teal-400 transition flex items-center justify-center gap-2">
                <Play className="w-5 h-5" />
                Start Bot
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Backtest Screen
const BacktestScreen = () => {
  return (
    <div className="flex-1 bg-slate-950 overflow-auto">
      <header className="border-b border-slate-800 px-8 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white">Backtesting</h2>
            <p className="text-slate-500 text-sm">Simulate strategies with historical data</p>
          </div>
          <button className="px-4 py-2 bg-teal-500 text-slate-900 font-semibold rounded-lg hover:bg-teal-400 transition flex items-center gap-2">
            <Play className="w-4 h-4" />
            Run Backtest
          </button>
        </div>
      </header>

      <div className="p-8">
        {/* Results Summary */}
        <div className="grid grid-cols-6 gap-4 mb-8">
          {[
            { label: 'Total Return', value: '+24.0%', color: 'text-teal-400' },
            { label: 'Sharpe Ratio', value: '1.82', color: 'text-white' },
            { label: 'Max Drawdown', value: '-8.4%', color: 'text-red-400' },
            { label: 'Win Rate', value: '68.5%', color: 'text-cyan-400' },
            { label: 'Total Trades', value: '342', color: 'text-white' },
            { label: 'Profit Factor', value: '2.14', color: 'text-teal-400' },
          ].map((stat, i) => (
            <div key={i} className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-center">
              <p className={`text-2xl font-bold ${stat.color}`}>{stat.value}</p>
              <p className="text-xs text-slate-500 mt-1">{stat.label}</p>
            </div>
          ))}
        </div>

        {/* Chart */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 mb-8">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-white">Performance vs Benchmark (Hold)</h3>
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-teal-400" />
                <span className="text-slate-400 text-sm">Strategy</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-slate-500" />
                <span className="text-slate-400 text-sm">Hold</span>
              </div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={backtestData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={12} />
              <YAxis stroke="#64748b" fontSize={12} />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#0f172a', 
                  border: '1px solid #1e293b',
                  borderRadius: '12px',
                  color: '#fff'
                }} 
              />
              <Line type="monotone" dataKey="portfolio" stroke="#14b8a6" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="benchmark" stroke="#64748b" strokeWidth={2} dot={false} strokeDasharray="5 5" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Detailed Stats */}
        <div className="grid grid-cols-2 gap-8">
          {/* Monthly Returns */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Monthly Returns</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={[
                { month: 'Jan', return: 8 },
                { month: 'Feb', return: -2 },
                { month: 'Mar', return: 12 },
                { month: 'Apr', return: 5 },
                { month: 'May', return: -4 },
                { month: 'Jun', return: 15 },
              ]}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="month" stroke="#64748b" fontSize={12} />
                <YAxis stroke="#64748b" fontSize={12} />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#0f172a', 
                    border: '1px solid #1e293b',
                    borderRadius: '12px',
                    color: '#fff'
                  }} 
                />
                <Bar dataKey="return" fill="#14b8a6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Trade Distribution */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Trade Distribution</h3>
            <div className="space-y-4">
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-slate-400">Winning Trades</span>
                  <span className="text-teal-400 font-semibold">234 (68.5%)</span>
                </div>
                <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                  <div className="h-full bg-teal-500 rounded-full" style={{ width: '68.5%' }} />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-slate-400">Losing Trades</span>
                  <span className="text-red-400 font-semibold">108 (31.5%)</span>
                </div>
                <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                  <div className="h-full bg-red-500 rounded-full" style={{ width: '31.5%' }} />
                </div>
              </div>
              <div className="pt-4 border-t border-slate-800">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-slate-500 text-xs">Avg Win</p>
                    <p className="text-teal-400 font-bold">+2.34%</p>
                  </div>
                  <div>
                    <p className="text-slate-500 text-xs">Avg Loss</p>
                    <p className="text-red-400 font-bold">-1.12%</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Telegram Bot Screen
const TelegramScreen = () => {
  const messages = [
    { type: 'bot', text: '🤖 Welcome to AutoGrid Bot!\n\nChoose an option:', time: '14:30' },
    { type: 'user', text: '/portfolio', time: '14:31' },
    { type: 'bot', text: '📊 **Your Portfolio**\n\n💰 Balance: $14,280.00\n📈 24h Profit: +$342 (+2.4%)\n\n**Positions:**\n• BTC: 0.15 ($6,487)\n• ETH: 2.3 ($5,244)\n• SOL: 25.0 ($2,460)', time: '14:31' },
    { type: 'user', text: '/buy BTC 100', time: '14:32' },
    { type: 'bot', text: '✅ **Order Executed!**\n\n🔵 BUY BTC/USDT\n💵 Amount: $100.00\n📍 Price: $43,250.00\n📦 Quantity: 0.00231 BTC\n\n💳 Fee: $0.50 (0.5%)', time: '14:32' },
  ];

  return (
    <div className="flex-1 bg-slate-950 overflow-auto">
      <header className="border-b border-slate-800 px-8 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white">Telegram Bot</h2>
            <p className="text-slate-500 text-sm">Trade via chat, get real-time alerts</p>
          </div>
          <button className="px-4 py-2 bg-cyan-500 text-slate-900 font-semibold rounded-lg hover:bg-cyan-400 transition flex items-center gap-2">
            <Send className="w-4 h-4" />
            Connect Telegram
          </button>
        </div>
      </header>

      <div className="p-8">
        <div className="grid grid-cols-3 gap-8">
          {/* Phone Mockup */}
          <div className="col-span-1">
            <div className="bg-slate-900 rounded-[3rem] p-3 border-4 border-slate-800 max-w-[320px] mx-auto">
              <div className="bg-slate-950 rounded-[2.5rem] overflow-hidden">
                {/* Status Bar */}
                <div className="bg-slate-900 px-6 py-2 flex items-center justify-between text-xs text-slate-400">
                  <span>14:32</span>
                  <div className="flex gap-1">
                    <div className="w-4 h-2 bg-slate-600 rounded-sm" />
                    <div className="w-4 h-2 bg-slate-600 rounded-sm" />
                    <div className="w-6 h-3 bg-teal-500 rounded-sm" />
                  </div>
                </div>
                
                {/* Chat Header */}
                <div className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex items-center gap-3">
                  <div className="w-10 h-10 bg-gradient-to-br from-teal-400 to-cyan-500 rounded-full flex items-center justify-center">
                    <Layers className="w-5 h-5 text-slate-900" />
                  </div>
                  <div>
                    <p className="text-white font-semibold text-sm">AutoGrid Bot</p>
                    <p className="text-teal-400 text-xs">Online</p>
                  </div>
                </div>

                {/* Messages */}
                <div className="h-80 p-4 space-y-3 overflow-y-auto">
                  {messages.map((msg, i) => (
                    <div key={i} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[80%] p-3 rounded-2xl text-xs ${
                        msg.type === 'user' 
                          ? 'bg-teal-500 text-slate-900 rounded-br-sm' 
                          : 'bg-slate-800 text-white rounded-bl-sm'
                      }`}>
                        <p className="whitespace-pre-line">{msg.text}</p>
                        <p className={`text-[10px] mt-1 ${msg.type === 'user' ? 'text-teal-800' : 'text-slate-500'}`}>
                          {msg.time}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Input */}
                <div className="bg-slate-900 border-t border-slate-800 p-3 flex gap-2">
                  <input 
                    type="text" 
                    placeholder="Type a command..." 
                    className="flex-1 bg-slate-800 rounded-full px-4 py-2 text-xs text-white placeholder-slate-500"
                  />
                  <button className="w-8 h-8 bg-teal-500 rounded-full flex items-center justify-center">
                    <Send className="w-4 h-4 text-slate-900" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Commands & Features */}
          <div className="col-span-2 space-y-6">
            {/* Commands */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Available Commands</h3>
              <div className="grid grid-cols-2 gap-4">
                {[
                  { cmd: '/portfolio', desc: 'View balance & positions' },
                  { cmd: '/buy <pair> <amount>', desc: 'Buy crypto' },
                  { cmd: '/sell <pair> <amount>', desc: 'Sell crypto' },
                  { cmd: '/price <pair>', desc: 'Get current price' },
                  { cmd: '/bots', desc: 'List active bots' },
                  { cmd: '/alerts', desc: 'Configure alerts' },
                  { cmd: '/history', desc: 'Trade history' },
                  { cmd: '/help', desc: 'List all commands' },
                ].map((item, i) => (
                  <div key={i} className="flex items-center gap-3 p-3 bg-slate-800/50 rounded-xl">
                    <code className="text-teal-400 font-mono text-sm">{item.cmd}</code>
                    <span className="text-slate-400 text-sm">— {item.desc}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Pricing */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Bot Monetization</h3>
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-4 bg-slate-800/50 rounded-xl">
                  <p className="text-3xl font-bold text-white">0.5%</p>
                  <p className="text-slate-400 text-sm mt-1">Fee per trade</p>
                </div>
                <div className="text-center p-4 bg-slate-800/50 rounded-xl">
                  <p className="text-3xl font-bold text-teal-400">Free</p>
                  <p className="text-slate-400 text-sm mt-1">Queries & alerts</p>
                </div>
                <div className="text-center p-4 bg-slate-800/50 rounded-xl">
                  <p className="text-3xl font-bold text-cyan-400">50%</p>
                  <p className="text-slate-400 text-sm mt-1">White-label rev share</p>
                </div>
              </div>
            </div>

            {/* Features */}
            <div className="grid grid-cols-3 gap-4">
              {[
                { icon: Zap, title: 'Instant Execution', desc: 'Trades in <500ms' },
                { icon: Shield, title: 'Secure', desc: 'Trade-only, no withdraw' },
                { icon: Bell, title: '24/7 Alerts', desc: 'Real-time notifications' },
              ].map((feat, i) => (
                <div key={i} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                  <feat.icon className="w-8 h-8 text-teal-400 mb-3" />
                  <h4 className="text-white font-semibold">{feat.title}</h4>
                  <p className="text-slate-400 text-sm mt-1">{feat.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Pricing Screen
const PricingScreen = () => {
  const plans = [
    {
      name: 'Free',
      subtitle: 'Open Source',
      price: '$0',
      period: 'forever',
      color: 'slate',
      features: [
        'Core bot engine',
        'Grid + DCA strategies',
        '1 exchange',
        'CLI interface',
        'Basic backtesting',
        'Full documentation',
      ],
      cta: 'Download on GitHub',
      popular: false,
    },
    {
      name: 'Starter',
      subtitle: 'Cloud',
      price: '$9',
      period: '/month',
      color: 'cyan',
      features: [
        'Everything in Free +',
        '2 concurrent bots',
        '2 exchanges',
        'Web dashboard',
        'Email alerts',
        'Email support',
      ],
      cta: 'Start Free Trial',
      popular: false,
    },
    {
      name: 'Pro',
      subtitle: 'Cloud',
      price: '$29',
      period: '/month',
      color: 'teal',
      features: [
        'Everything in Starter +',
        '10 concurrent bots',
        '5 exchanges',
        'Telegram Bot',
        'Advanced backtesting',
        'Priority support',
      ],
      cta: 'Choose Pro',
      popular: true,
    },
    {
      name: 'Enterprise',
      subtitle: 'White-Label',
      price: '$49',
      period: '/month',
      color: 'violet',
      features: [
        'Everything in Pro +',
        'Unlimited bots',
        'All exchanges',
        'Public API',
        'White-label Telegram',
        'Dedicated support',
      ],
      cta: 'Contact Sales',
      popular: false,
    },
  ];

  return (
    <div className="flex-1 bg-slate-950 overflow-auto">
      <header className="border-b border-slate-800 px-8 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white">Pricing</h2>
            <p className="text-slate-500 text-sm">Choose the plan that fits your needs</p>
          </div>
        </div>
      </header>

      <div className="p-8">
        {/* Toggle */}
        <div className="flex justify-center mb-12">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-1 flex gap-1">
            <button className="px-6 py-2 bg-teal-500 text-slate-900 font-semibold rounded-lg">
              Monthly
            </button>
            <button className="px-6 py-2 text-slate-400 font-medium rounded-lg hover:text-white transition">
              Yearly (-20%)
            </button>
          </div>
        </div>

        {/* Plans Grid */}
        <div className="grid grid-cols-4 gap-6 max-w-6xl mx-auto">
          {plans.map((plan, i) => (
            <div
              key={i}
              className={`relative bg-slate-900 border rounded-2xl p-6 ${
                plan.popular ? 'border-teal-500 ring-2 ring-teal-500/20' : 'border-slate-800'
              }`}
            >
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-teal-500 text-slate-900 text-xs font-bold rounded-full">
                  POPULAR
                </div>
              )}

              <div className="text-center mb-6">
                <p className={`text-${plan.color}-400 text-sm font-medium`}>{plan.subtitle}</p>
                <h3 className="text-2xl font-bold text-white mt-1">{plan.name}</h3>
                <div className="mt-4">
                  <span className="text-4xl font-bold text-white">{plan.price}</span>
                  <span className="text-slate-500">{plan.period}</span>
                </div>
              </div>

              <ul className="space-y-3 mb-8">
                {plan.features.map((feat, j) => (
                  <li key={j} className="flex items-center gap-2 text-sm">
                    <Check className={`w-4 h-4 text-${plan.color}-400`} />
                    <span className="text-slate-300">{feat}</span>
                  </li>
                ))}
              </ul>

              <button
                className={`w-full py-3 rounded-xl font-semibold transition ${
                  plan.popular
                    ? 'bg-teal-500 text-slate-900 hover:bg-teal-400'
                    : 'bg-slate-800 text-white hover:bg-slate-700'
                }`}
              >
                {plan.cta}
              </button>
            </div>
          ))}
        </div>

        {/* FAQ */}
        <div className="max-w-3xl mx-auto mt-16">
          <h3 className="text-xl font-bold text-white text-center mb-8">Frequently Asked Questions</h3>
          <div className="space-y-4">
            {[
              { q: 'Can I cancel anytime?', a: 'Yes, no contracts or cancellation fees.' },
              { q: 'Are my API keys safe?', a: 'Yes, encrypted with AES-256 and never logged.' },
              { q: 'What\'s the difference between Free and Cloud?', a: 'Free is self-hosted (you manage the server). Cloud is hosted by us 24/7.' },
            ].map((faq, i) => (
              <div key={i} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <p className="text-white font-medium">{faq.q}</p>
                <p className="text-slate-400 text-sm mt-2">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

// Main App
export default function AutoGridWireframes() {
  const [activeScreen, setActiveScreen] = useState('dashboard');

  const renderScreen = () => {
    switch (activeScreen) {
      case 'dashboard': return <DashboardScreen />;
      case 'bots': return <BotsScreen />;
      case 'backtest': return <BacktestScreen />;
      case 'telegram': return <TelegramScreen />;
      case 'pricing': return <PricingScreen />;
      default: return <DashboardScreen />;
    }
  };

  return (
    <div className="flex h-screen bg-slate-950 text-white font-sans">
      <Sidebar activeScreen={activeScreen} setActiveScreen={setActiveScreen} />
      {renderScreen()}
    </div>
  );
}
