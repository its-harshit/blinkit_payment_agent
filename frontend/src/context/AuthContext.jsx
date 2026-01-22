import React, { createContext, useContext, useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { authAPI } from '../services/api'

const AuthContext = createContext()

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(localStorage.getItem('access_token'))
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    // Check if user is authenticated
    if (token) {
      // Verify token is still valid (simple check for POC)
      setUser({ token })
      setLoading(false)
    } else {
      setLoading(false)
    }
  }, [token])

  const login = async (mobileNumber) => {
    try {
      const response = await authAPI.login(mobileNumber)
      return { success: true, data: response.data }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.detail || 'Login failed',
      }
    }
  }

  const verifyOTP = async (mobileNumber, otp) => {
    try {
      const response = await authAPI.verifyOTP(mobileNumber, otp)
      const { access_token, user } = response.data
      
      localStorage.setItem('access_token', access_token)
      setToken(access_token)
      setUser(user)
      
      return { success: true, data: response.data }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.detail || 'OTP verification failed',
      }
    }
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    setToken(null)
    setUser(null)
    navigate('/login')
  }

  const value = {
    user,
    token,
    loading,
    isAuthenticated: !!user && !!token,
    login,
    verifyOTP,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
