import akshare as ak
import backtrader as bt
import pandas as pd
import matplotlib.pyplot as plt

class DualMAStrategy(bt.Strategy):
    # 注意类名拼写：Strategy 不是 Startegy，不影响运行但建议改
    params = (("fast", 5), ("slow", 20))

    def __init__(self):
        self.fast_ma = bt.indicators.SMA(period=self.p.fast)
        self.slow_ma = bt.indicators.SMA(period=self.p.slow)

    def next(self):
        if not self.position:
            if self.fast_ma[0] > self.slow_ma[0]:
                self.buy()
        elif self.fast_ma[0] < self.slow_ma[0]:
            self.close()

class DualMAStrategy_with_StopLoss(bt.Strategy):
    params = (("fast", 5), ("slow", 20), ("stop_loss_pct", 0.05))

    def __init__(self):
        self.fast_ma = bt.indicators.SMA(period=self.p.fast)
        self.slow_ma = bt.indicators.SMA(period=self.p.slow)
        self.trend_ma = bt.indicators.SMA(period=60) 
        self.buy_price = None 
        self.stop_order = None # ✅ 新增：用来记录止损单

    def notify_order(self, order):
        # ✅ 如果止损单被取消或完成，清空记录
        if order.status in [order.Completed, order.Canceled, order.Margin]:
            if order == self.stop_order:
                self.stop_order = None
            if order.status == order.Completed:
                if order.isbuy():
                    self.buy_price = order.executed.price
                elif order.issell():
                    self.buy_price = None

    def next(self):
        if not self.position:
            # 如果有未完成的止损单，先取消
            if self.stop_order is not None:
                self.cancel(self.stop_order)
                
            if self.fast_ma[0] > self.slow_ma[0] and self.data.close[0] > self.trend_ma[0]:
                self.buy()
        else:
            # ✅ 如果持仓了，且还没挂止损单，就在盘中挂一个 Stop 单
            if self.stop_order is None:
                stop_price = self.buy_price * (1 - self.p.stop_loss_pct)
                # 这是一个“跌破 stop_price 就市价卖出”的指令
                self.stop_order = self.sell(exectype=bt.Order.Stop, price=stop_price)
                print(f"挂载止损单！买入价: {self.buy_price:.2f}, 止损线: {stop_price:.2f}")
            
            # 正常死叉卖出逻辑
            if self.fast_ma[0] < self.slow_ma[0]:
                # 如果死叉了，取消止损单，直接市价清仓
                if self.stop_order is not None:
                    self.cancel(self.stop_order)
                self.close()



def test(symbol="sz000001", 
         start_date="20240101",
         end_date="20241125", 
         Sizers = "percent",
         strategy=DualMAStrategy,
         stake=100,
         origin_cash = 50000,

         ):
    """
    Args:
        symbol: 腾讯源股票代码，如 "sz000001"。
        start_date: 开始日期，格式 YYYYMMDD。
        end_date: 结束日期，格式 YYYYMMDD。
        Sizers: 加仓方式
        strategy: bt.Strategy 子类。
        stake: 每次买入股数，最低 100。
        origin_cash: 起始资金。

    Returns:
        None，结果直接打印并绘图。
    """
    print(f"=============== {symbol}: {start_date} --- {end_date} ===============")

    df = ak.stock_zh_a_hist_tx(
        symbol=symbol, start_date=start_date,
        end_date=end_date, adjust="qfq"
    )

    # ✅ 关键修正 1：统一列名（腾讯源的成交量字段叫 amount）
    df = df.rename(columns={"amount": "volume"})
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    data = bt.feeds.PandasData(
        dataname=df[["open", "high", "low", "close", "volume"]]
    )

    cerebro = bt.Cerebro()
    cerebro.broker.setcommission(commission=0.0005)      # 万五佣金
    cerebro.broker.set_slippage_fixed(fixed=0.01)        # 1 分钱滑点
    cerebro.adddata(data)
    cerebro.addstrategy(strategy)
    cerebro.broker.setcash(origin_cash)
    if Sizers == "fixed":
        cerebro.addsizer(bt.sizers.FixedSize, stake=stake)
    if Sizers == "percent":
        cerebro.addsizer(bt.sizers.PercentSizer, percents = 95)

    # ✅ 关键修正 2：加入绩效分析器（否则只能看到资金变化）
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")

    print(f"回测前资金: {cerebro.broker.getvalue():.2f}")
    results = cerebro.run()
    strat = results[0]

    final_value = cerebro.broker.getvalue()
    print(f"回测后资金: {final_value:.2f}")

    # ✅ 关键修正 3：打印核心绩效指标（这比总收益率有意义得多）
    returns = strat.analyzers.returns.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    sharpe = strat.analyzers.sharpe.get_analysis()

    print(f"总收益率: {returns['rtot'] * 100:.2f}%")
    print(f"最大回撤: {drawdown['max']['drawdown']:.2f}%")
    print(f"夏普比率: {sharpe.get('sharperatio', 'N/A')}")

    cerebro.plot()  # 第一次先注释掉，确认逻辑跑通后再打开

def test2(symbol="sz000001", 
         start_date="20240101",
         end_date="20241125", 
         Sizers = "percent",
         strategy=DualMAStrategy,
         stake=100,
         origin_cash = 50000,
         plot = False,
         fast = 5,
         slow = 20
         ):
    """
    Args:
        symbol: 腾讯源股票代码，如 "sz000001"。
        start_date: 开始日期，格式 YYYYMMDD。
        end_date: 结束日期，格式 YYYYMMDD。
        Sizers: 加仓方式
        strategy: bt.Strategy 子类。
        stake: 每次买入股数，最低 100。
        origin_cash: 起始资金。
        plot: 是否展示k线图
        slow: 策略中的slow参数
        fast: 策略中的fast参数
    Returns:
        None，结果直接打印并绘图。
    """
    print(f"=============== {symbol}: {start_date} --- {end_date} ===============")

    df = ak.stock_zh_a_hist_tx(
        symbol=symbol, start_date=start_date,
        end_date=end_date, adjust="qfq"
    )

    df = df.rename(columns={"amount": "volume"})
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    data = bt.feeds.PandasData(
        dataname=df[["open", "high", "low", "close", "volume"]]
    )

    cerebro = bt.Cerebro()
    cerebro.broker.setcommission(commission=0.0005)
    cerebro.broker.set_slippage_fixed(fixed=0.01)
    cerebro.adddata(data)
    cerebro.addstrategy(strategy, fast=fast, slow=slow)
    cerebro.broker.setcash(origin_cash)
    
    if Sizers == "fixed":
        cerebro.addsizer(bt.sizers.FixedSize, stake=stake)
    if Sizers == "percent":
        cerebro.addsizer(bt.sizers.PercentSizer, percents = 95)

    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio, 
        _name="sharpe",
        timeframe=bt.TimeFrame.Days,  # 告诉它数据是日线
        compression=1,                # 每天的频率
        riskfreerate=0.0,             # 无风险利率设为 0（新手回测通常设为0即可）
        annualize=True,               # 强制开启年化
        factor=252                    # 一年 252 个交易日，让引擎自己换算
    )
    
    # ✅ 新增：添加一个记录每日收益率的分析器
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn")

    print(f"回测前资金: {cerebro.broker.getvalue():.2f}")
    results = cerebro.run()
    strat = results[0]

    final_value = cerebro.broker.getvalue()
    print(f"回测后资金: {final_value:.2f}")

    returns = strat.analyzers.returns.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    sharpe = strat.analyzers.sharpe.get_analysis()

    print(f"总收益率: {returns['rtot'] * 100:.2f}%")
    print(f"最大回撤: {drawdown['max']['drawdown']:.2f}%")
    print(f"夏普比率: {sharpe.get('sharperatio', 0)}")

    # ✅ 注释掉原来的K线图，我们改用外部画图
    if plot:
        cerebro.plot()  
    
    # ✅ 提取每日收益率，并转换成资金净值曲线
    # TimeReturn 返回的是每日的收益率（如 0.01 代表涨1%）
    time_return = strat.analyzers.timereturn.get_analysis()
    # 将收益率转为 Series，+1 后累乘，算出每天的净值（起点为1）
    nav_series = (pd.Series(time_return) + 1).cumprod()
    sharpe_val = sharpe.get('sharperatio', 0)
    # ✅ 返回这个净值数据，供主程序画图
    return {
        "nav": nav_series,           # 每日净值曲线
        "returns": returns['rtot'] * 100, # 总收益率
        "sharpe": sharpe_val         # 夏普比率
    }


def test_single_and_drawdown(symbol="sz000001", 
         start_date="20240101",
         end_date="20241125", 
         Sizers = "percent",
         strategy=DualMAStrategy,
         stake=100,
         origin_cash = 50000,
         plot = False,
         fast = 5,
         slow = 20
         ):
    """
    Args:
        symbol: 腾讯源股票代码，如 "sz000001"。
        start_date: 开始日期，格式 YYYYMMDD。
        end_date: 结束日期，格式 YYYYMMDD。
        Sizers: 加仓方式
        strategy: bt.Strategy 子类。
        stake: 每次买入股数，最低 100。
        origin_cash: 起始资金。
        plot: 是否展示k线图
        slow: 策略中的slow参数
        fast: 策略中的fast参数
    Returns:
        None，结果直接打印并绘图。
    """
    print(f"=============== {symbol}: {start_date} --- {end_date} ===============")

    df = ak.stock_zh_a_hist_tx(
        symbol=symbol, start_date=start_date,
        end_date=end_date, adjust="qfq"
    )

    df = df.rename(columns={"amount": "volume"})
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)

    data = bt.feeds.PandasData(
        dataname=df[["open", "high", "low", "close", "volume"]]
    )

    cerebro = bt.Cerebro()
    cerebro.broker.setcommission(commission=0.0005)
    cerebro.broker.set_slippage_fixed(fixed=0.01)
    cerebro.adddata(data)
    cerebro.addstrategy(strategy, fast=fast, slow=slow)
    cerebro.broker.setcash(origin_cash)
    
    if Sizers == "fixed":
        cerebro.addsizer(bt.sizers.FixedSize, stake=stake)
    if Sizers == "percent":
        cerebro.addsizer(bt.sizers.PercentSizer, percents = 95)

    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio, 
        _name="sharpe",
        timeframe=bt.TimeFrame.Days,  # 告诉它数据是日线
        compression=1,                # 每天的频率
        riskfreerate=0.0,             # 无风险利率设为 0（新手回测通常设为0即可）
        annualize=True,               # 强制开启年化
        factor=252                    # 一年 252 个交易日，让引擎自己换算
    )
    
    # ✅ 新增：添加一个记录每日收益率的分析器
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn")

    print(f"回测前资金: {cerebro.broker.getvalue():.2f}")
    results = cerebro.run()
    strat = results[0]

    final_value = cerebro.broker.getvalue()
    print(f"回测后资金: {final_value:.2f}")

    returns = strat.analyzers.returns.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    sharpe = strat.analyzers.sharpe.get_analysis()

    print(f"总收益率: {returns['rtot'] * 100:.2f}%")
    print(f"最大回撤: {drawdown['max']['drawdown']:.2f}%")
    print(f"夏普比率: {sharpe.get('sharperatio', 0)}")
    
    # ✅ 注释掉原来的K线图，我们改用外部画图
    if plot:
        cerebro.plot()  
    
    # ✅ 提取每日收益率，并转换成资金净值曲线
    # TimeReturn 返回的是每日的收益率（如 0.01 代表涨1%）
    time_return = strat.analyzers.timereturn.get_analysis()
    # 将收益率转为 Series，+1 后累乘，算出每天的净值（起点为1）
    nav_series = (pd.Series(time_return) + 1).cumprod()

    cum_max = nav_series.cummax()                      # 历史上的最高净值
    drawdown_series = (nav_series / cum_max) - 1       # 每日的回撤比例
    max_dd_date = drawdown_series.idxmin()             # 回撤最深的那一天
    max_dd_val = drawdown_series.min() * 100           # 回撤的具体数值
    
    print(f"🔥 最大回撤发生日期: {max_dd_date.date()}, 比例: {max_dd_val:.2f}%")
    
    sharpe_val = sharpe.get('sharperatio', 0)
    # ✅ 返回这个净值数据，供主程序画图
    return {
        "nav": nav_series,           # 每日净值曲线
        "returns": returns['rtot'] * 100, # 总收益率
        "sharpe": sharpe_val         # 夏普比率
    }

if __name__ == "__main__":
    test_single_and_drawdown(symbol="sh510300",start_date='20240101',end_date='20250103', fast =5 ,slow = 20, strategy=DualMAStrategy_with_StopLoss,plot=True)