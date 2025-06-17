const config = require('../config/config')

module.exports = {
  verifyApiToken(req, res, next) {
    try {
      // Get token from Authorization header
      const authHeader = req.headers.authorization
      
      if (!authHeader) {
        return res.status(401).json({
          error: "No authorization header provided"
        })
      }

      // Extract token from "Bearer TOKEN" or just "TOKEN"
      const token = authHeader.startsWith('Bearer ') 
        ? authHeader.slice(7) 
        : authHeader

      if (!token) {
        return res.status(401).json({
          error: "No token provided"
        })
      }

      // Check if token matches hardcoded value
      if (token !== config.authentication.apiAccessToken) {
        return res.status(401).json({
          error: "Invalid API token"
        })
      }

      // Token is valid, continue to next middleware/route handler
      next()

    } catch (error) {
      console.error('API Token verification error:', error)
      return res.status(500).json({
        error: "Token verification failed"
      })
    }
  }
}
