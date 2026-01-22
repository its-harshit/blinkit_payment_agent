import { TrendingUp, Calendar, CreditCard, CheckCircle2, XCircle, Clock, Smartphone, Copy } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useState } from 'react'

const Dashboard = ({ data }) => {
  const { transactions = [], mandates = [] } = data
  const { user } = useAuth()
  const [copied, setCopied] = useState(false)
  const [txnFilter, setTxnFilter] = useState('ALL')
  
  // Generate VPA from mobile number
  const mobileNumber = user?.mobile_number || '9876543210'
  const vpa = `${mobileNumber}@paytm`
  
  const copyToClipboard = () => {
    navigator.clipboard.writeText(vpa)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const getStatusIcon = (status) => {
    switch (status) {
      case 'Success':
        return <CheckCircle2 className="w-3 h-3" />
      case 'Failed':
        return <XCircle className="w-3 h-3" />
      case 'Pending':
        return <Clock className="w-3 h-3" />
      default:
        return null
    }
  }

  return (
    <div className="mt-3 mb-3 border border-[#D6D6D6] rounded-2xl p-4 sm:p-5 shadow-sm">
      {/* VPA Info Section */}
      <div className="mb-6">
        <div className="bg-yellow-100 rounded-xl p-5 shadow-md">
          <div className="flex items-start gap-4">
            <div className="p-2.5 bg-[#26387E] rounded-lg flex-shrink-0 shadow-sm">
              <Smartphone className="w-6 h-6 text-white" />
            </div>
            <div className="flex-1 min-w-0 mt-1">
              <div className="text-gray-900 text-sm sm:text-base leading-relaxed">
                <span className="opacity-90">This VPA</span>
                <span className="font-semibold text-xl sm:text-xl px-1 rounded">
                  {vpa}
                </span>
                <span className="opacity-90">is linked to your 
                <span className="font-semibold text-xl sm:text-xl px-1 rounded">
                UPI Number
                </span>on</span>
                <span className="font-semibold text-xl sm:text-xl px-1 rounded">
                Paytm App
                </span>
                <span className="opacity-90">.</span>
              </div>
              <div className="text-gray-900 text-xs sm:text-base opacity-90 mt-2">
                Money sent to your mobile number will be credited here.
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Header */}
      <div className="mb-6 pb-4 border-b border-[#D6D6D6]">
        <div className="flex items-center gap-3 mb-2">
        <div className="w-1 h-9 bg-[#F47920] rounded-full mr-2"></div>
          <h3 className="text-xl sm:text-2xl font-bold text-gray-900">
            Payment Details
          </h3>
        </div>
      </div>

      {/* Transactions Section */}
      {transactions.length > 0 && (
        <div className="mb-10">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-[#E55C11]" />
            <h4 className="text-base sm:text-xl font-semibold text-gray-900">Recent Transactions</h4>
            <span className="ml-auto px-4 py-2 bg-gray-200 text-gray-900 rounded-full text-lg font-semibold">
              Last 10
            </span>
          </div>

          {/* Filter Tabs */}
          <div className="flex gap-2 mb-3">
            {['ALL', 'P2P', 'P2M'].map((tab) => (
              <button
                key={tab}
                onClick={() => setTxnFilter(tab)}
                className={`px-3 py-1.5 rounded-full text-sm font-semibold border transition ${
                  txnFilter === tab
                    ? 'bg-orange-400 text-white border-orange-400'
                    : 'bg-white text-gray-700 border-[#D6D6D6] hover:bg-gray-50'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          <div className="overflow-x-auto rounded-xl border border-[#D6D6D6] bg-white">
            <table className="w-full text-sm sm:text-base">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left py-2.5 px-4 font-semibold text-gray-700">Date</th>
                  <th className="text-left py-2.5 px-4 font-semibold text-gray-700">Merchant</th>
                  <th className="text-right py-2.5 px-4 font-semibold text-gray-700">Amount</th>
                  <th className="text-center py-2.5 px-4 font-semibold text-gray-700">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {transactions
                  .filter((txn) => txnFilter === 'ALL' || (txn.txn_type || '').toUpperCase() === txnFilter)
                  .map((txn, index) => (
                  <tr 
                    key={txn.id} 
                    className={`hover:bg-gray-50 transition-colors ${
                      index % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'
                    }`}
                  >
                    <td className="py-2.5 px-4">
                      <div className="flex items-start gap-2">
                        <Calendar className="w-4 h-4 text-gray-400 mt-0.5" />
                        <div className="flex flex-col">
                          <span className="text-gray-700 font-medium">
                            {new Date(txn.date).toLocaleDateString('en-IN', { 
                              day: '2-digit', 
                              month: 'short', 
                              year: 'numeric' 
                            })}
                          </span>
                          <span className="text-gray-500 text-xs mt-0.5">
                            {new Date(txn.date).toLocaleTimeString('en-IN', { 
                              hour: '2-digit', 
                              minute: '2-digit',
                              hour12: true
                            })}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="py-2.5 px-4">
                      <span className="text-gray-900 font-semibold">{txn.merchant}</span>
                    </td>
                    <td className="py-2.5 px-4 text-right">
                      <span className="font-bold text-[#E55C11] text-base">
                        ₹{txn.amount.toLocaleString('en-IN')}
                      </span>
                    </td>
                    <td className="py-2.5 px-4">
                      <div className="flex justify-center">
                        <span
                          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold ${
                            txn.status === 'Success'
                              ? 'bg-green-100 text-green-800 border border-green-200'
                              : txn.status === 'Failed'
                              ? 'bg-red-100 text-red-800 border border-red-200'
                              : 'bg-yellow-100 text-yellow-800 border border-yellow-200'
                          }`}
                        >
                          {getStatusIcon(txn.status)}
                          {txn.status}
                        </span>
                      </div>
                    </td>
                      {/* <td className="py-3 px-4">
                        <span className="text-gray-600 text-xs font-mono bg-gray-100 px-2 py-1 rounded">
                          {txn.upi_id}
                        </span>
                      </td> */}
                  </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Mandates Section */}
      {mandates.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-5">
            <div className="w-1 h-6 bg-[#F47920] rounded-full mr-2"></div>
            <h4 className="text-base sm:text-xl font-semibold text-gray-900">Active Mandates</h4>
            <span className="ml-auto px-4 py-2 bg-gray-200 text-gray-900 rounded-full text-lg font-semibold">
              {mandates.length} Active
            </span>
          </div>
          <div className="grid gap-6 sm:gap-5 md:grid-cols-2 lg:grid-cols-2">
            {mandates.map((mandate, idx) => {
              // Use provided labels or deterministic fallbacks so we always show a bank/card label
              const fallbackLabels = [
                'ICICI Credit Card ••99',
                'SBI Bank ••45',
                'HDFC Bank ••12',
                'Axis Credit Card ••63',
                'Kotak Bank ••07',
                'Paytm Wallet'
              ];
              const accountLabel = mandate.account_label || fallbackLabels[idx % fallbackLabels.length];
              const accountType =
                mandate.account_type ||
                (accountLabel.toLowerCase().includes('card') ? 'CREDIT' : 'ACCOUNT');
              return (
                <div
                  key={mandate.id}
                  className="group relative bg-white border border-[#D6D6D6] rounded-2xl p-4 sm:p-5 hover:shadow-lg transition-all duration-200"
                >
                  {/* Header row: Merchant + Status */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1 min-w-0 pr-3">
                      <h5 className="font-bold text-gray-900 text-lg leading-tight truncate">{mandate.merchant}</h5>
                    </div>
                    <span className="inline-flex items-center gap-1 px-3 py-1.5 bg-green-100 text-green-800 text-sm rounded-full font-semibold border border-green-200 whitespace-nowrap">
                      <CheckCircle2 className="w-4 h-4" />
                      {mandate.status}
                    </span>
                  </div>

                  {/* Amount + Payment handle */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex flex-col">
                      <span className="text-[#E55C11] font-bold text-2xl leading-tight">
                        ₹{mandate.amount.toLocaleString('en-IN')}
                      </span>
                    </div>
                    <div className="text-right">
                      <div className="text-lg text-gray-800 font-semibold">{accountLabel}</div>
                      <div className="text-sm text-gray-600 uppercase mt-0.5">{accountType}</div>
                    </div>
                  </div>

                  {/* Frequency + Next debit */}
                  <div className="flex items-start justify-between text-sm text-gray-700 mb-3">
                    <div className="flex flex-col gap-1">
                      <div className="text-base">Frequency: <span className="font-semibold">{mandate.frequency}</span></div>
                      {/* <div className="text-base">Next debit: <span className="font-semibold">{new Date(mandate.next_debit_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}</span></div> */}
                    </div>
                    {/* <div className="text-right">
                      <div className="text-xs text-gray-500">Recurring Payment</div>
                    </div> */}
                  </div>
                  {/* Actions */}
                  <div className="flex gap-3 pt-3 border-t border-gray-200">
                    <button className="flex-1 px-3 py-2 rounded-full border border-gray-300 text-gray-700 font-semibold hover:bg-gray-50 transition">
                      Pause
                    </button>
                    <button className="flex-1 px-3 py-2 rounded-full border border-gray-300 text-gray-700 font-semibold hover:bg-gray-50 transition">
                      Revoke
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {transactions.length === 0 && mandates.length === 0 && (
        <div className="text-center py-12">
          <div className="p-4 bg-gray-100 rounded-2xl inline-block mb-3">
            <CreditCard className="w-12 h-12 text-gray-400" />
          </div>
          <p className="text-gray-600 font-semibold">No payment details available</p>
        </div>
      )}
    </div>
  )
}

export default Dashboard
