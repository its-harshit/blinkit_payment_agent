import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'

const Login = () => {
  const [mobile, setMobile] = useState('')
  const [otp, setOtp] = useState('')
  const [showOtp, setShowOtp] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login, verifyOTP } = useAuth()
  const navigate = useNavigate()

  const validateMobile = (mobile) => {
    if (!mobile || mobile.length !== 10) {
      return 'Mobile number must be exactly 10 digits'
    }
    if (!/^[6-9]/.test(mobile)) {
      return 'Mobile number must start with 6, 7, 8, or 9'
    }
    return null
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    if (!showOtp) {
      // Step 1: Request OTP
      const mobileError = validateMobile(mobile)
      if (mobileError) {
        setError(mobileError)
        setLoading(false)
        return
      }

      const result = await login(mobile)
      if (result.success) {
        setShowOtp(true)
      } else {
        setError(result.error)
      }
    } else {
      // Step 2: Verify OTP
      if (otp.length !== 6) {
        setError('Please enter a valid 6-digit OTP')
        setLoading(false)
        return
      }

      const result = await verifyOTP(mobile, otp)
      if (result.success) {
        // Navigate to chat - will auto-send first message
        navigate('/chat')
      } else {
        setError(result.error)
      }
    }

    setLoading(false)
  }

  return (
    <div className="min-h-screen bg-white flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-lg p-8">
          <h2 className="text-2xl font-semibold text-gray-900 mb-6 text-center">
            {showOtp ? 'Enter Verification Code' : 'Login'}
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            {!showOtp ? (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Mobile Number
                </label>
                <input
                  type="tel"
                  value={mobile}
                  onChange={(e) => {
                    const value = e.target.value.replace(/\D/g, '')
                    if (value.length <= 10) {
                      setMobile(value)
                    }
                  }}
                  className="w-full px-4 py-3 border border-[#D6D6D6] rounded-lg focus:ring-2 focus:ring-[#E55C11] focus:border-transparent"
                  placeholder="9876543210"
                  maxLength="10"
                  required
                />
                <p className="mt-2 text-xs text-gray-500">
                  Please enter a mobile number which is linked to your account
                </p>
              </div>
            ) : (
              <div>
                <p className="text-sm text-gray-600 mb-4">
                  We have sent a 6-digit code. Please enter <strong>123456</strong> for POC.
                </p>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  OTP
                </label>
                <input
                  type="text"
                  value={otp}
                  onChange={(e) => {
                    const value = e.target.value.replace(/\D/g, '')
                    if (value.length <= 6) {
                      setOtp(value)
                    }
                  }}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-transparent text-center text-2xl tracking-widest"
                  placeholder="123456"
                  maxLength="6"
                  required
                />
                <button
                  type="button"
                  onClick={() => {
                    setShowOtp(false)
                    setOtp('')
                    setError('')
                  }}
                  className="mt-4 text-sm text-gray-600 hover:text-gray-800"
                >
                  ← Back
                </button>
              </div>
            )}

            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-600">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading || (!showOtp && mobile.length !== 10) || (showOtp && otp.length !== 6)}
              className={`w-full py-3 rounded-full font-medium transition-all ${
                loading || (!showOtp && mobile.length !== 10) || (showOtp && otp.length !== 6)
                  ? 'bg-gray-300 cursor-not-allowed'
                  : 'bg-gradient-to-r from-orange-600 to-orange-500 hover:shadow-lg text-white'
              }`}
            >
              {loading ? 'Processing...' : showOtp ? 'Verify OTP' : 'Continue'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

export default Login
