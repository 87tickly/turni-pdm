import { useState, useEffect, useCallback } from "react"
import { getMe, clearToken, getToken } from "@/lib/api"

interface User {
  id: number
  username: string
  is_admin: boolean
}

export function useAuth() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const checkAuth = useCallback(async () => {
    if (!getToken()) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      const me = await getMe()
      setUser(me)
    } catch {
      setUser(null)
      clearToken()
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  const logout = useCallback(() => {
    clearToken()
    setUser(null)
  }, [])

  return { user, loading, logout, refresh: checkAuth }
}
