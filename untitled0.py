from ib_insync import IB, Stock, Future, Forex, CFD, MarketOrder


# 1. Connect to your live account through IB Gateway
ib = IB()
await ib.connectAsync('127.0.0.1', 4001, clientId=10001)


print(ib.managedAccounts())
account = ib.managedAccounts()[0]  # pick the first account

# 2. Define the contract (Sirius XM Holdings on SMART, traded in USD)
contract = Stock('SIRI', 'SMART', 'USD')
order = MarketOrder('BUY', 1, account=account)



# 4. Place the order
trade = ib.placeOrder(contract, order)

# 5. Wait a few seconds for IB to process
ib.sleep(3)

# 6. Print the order status
print("Order status:", trade.orderStatus.status)
print("Filled:", trade.orderStatus.filled)
print("Avg Price:", trade.orderStatus.avgFillPrice)

trade


summary = await ib.accountSummaryAsync()
for s in summary:
    print(s)