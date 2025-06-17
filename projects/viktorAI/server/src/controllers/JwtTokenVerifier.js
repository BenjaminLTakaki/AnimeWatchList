const { User } = require("../models")
const jwt = require("jsonwebtoken")
const config = require("../config/config")

function jwtSignUserRefreshToken (user) {
    const one_week = 7 * 24 * 60 * 60
    return jwt.sign({ id: user._id, jwtV: user.jwtVersion }, config.authentication.jwtRefreshSecret, {
        expiresIn: one_week
    })
}
function jwtSignUserAccessToken (user) {
    const ten_min = 10 * 60
    return jwt.sign({ id: user._id }, config.authentication.jwtAccessSecret, {
        expiresIn: ten_min
    })
}


module.exports = {
    async accessTokenVerify (req, res, next) { // call this method if it fails call refreshTokenVerify

        let as = req.cookies.as

        if (!as) {
            return res.status(401).json({ error: 'No valid token provided.' })
        }

        try {
            verifiedAccessToken = jwt.verify(as, config.authentication.jwtAccessSecret)
            req.verifiedAccessToken = verifiedAccessToken
            return next()
        } catch (error) {
            return res.status(401).json({ error: 'Invalid or expired token.' })
        }
    },

    async refreshTokenVerify (req, res, next) {

        let ref = req.cookies.ref

        if (!ref) {
            return res.status(401).send({
                error: 'No token provided' })
          }

        try {

            const verifiedRefreshToken = jwt.verify(ref, config.authentication.jwtRefreshSecret)
            const { id, jwtV } = verifiedRefreshToken

            if (!id || !jwtV) {
                return res.status(401).send({
                    error: 'Something went wrong!' })
            }
    
            const jwtVValue = parseInt(jwtV, 10)
            if (isNaN(jwtVValue)) {
                return res.status(401).send({ 
                    error: 'Something went wrong!' })
            }
    
            const user = await User.findById(id)
              
            if (!user || user.jwtVersion !== jwtVValue) {
                return res.status(401).send({ 
                    error: 'Signed out' })
            }
    
            ref = jwtSignUserRefreshToken(user.toObject())
            as = jwtSignUserAccessToken(user.toObject())
    
            const options = {
                httpOnly: true,
                secure: true, // only set 'secure' when deploying
                sameSite: 'None',
                maxAge: 7 * 24 * 60 * 60 * 1000, // 7 days
                path: "/"}
    
            res
            .cookie('ref', ref, {
                httpOnly: true,
                secure: true, // only set 'secure' when deploying
                sameSite: 'None',
                maxAge: 7 * 24 * 60 * 60 * 1000, // 7 days
                path: "/refresh"
            })
            .cookie('as', as, options)
            .status(200)
            .json({ message: "successful" })

        } catch (error) {
            if (error.name === 'TokenExpiredError' || error.name === 'JsonWebTokenError') {
                return res.status(401).send({
                    error: 'Token expired or invalid'
                })
            }
        }
    },
    async getUserId (req, res) {

        let as = req.cookies.as
      
        if (!as) {
            return res.status(401).json({ error: 'No valid token provided.' })
        }
      
        try {
            verifiedAccessToken = jwt.verify(as, config.authentication.jwtAccessSecret)
            const { userId } = verifiedAccessToken
            return userId
        } catch (error) {
            return res.status(401).json({ error: 'Invalid or expired token.' })
        }
      }
}