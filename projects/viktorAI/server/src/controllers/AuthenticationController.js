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

// REMEMER TO TAKE OUT ALL SENSITIVE DATA

module.exports = {
    async register (req, res) {
        try{
        await User.create(req.body)

        res.send({
            success: true,
            message: 'Registration successful!'
        })

    } catch (err) {
        console.log(err)
        res.status(400).send({
            error: 'Username or email already taken.'
        })
    }
    },

    async login (req, res) {
        try{
            const {username, password} = req.body
            const user = await User.findOne({ username })

            if (!user) {
                return res.status(403).send({
                    error: 'Invalid login information'
                })
            }
            const isPasswordValid = await user.comparePassword(password)
            if (!isPasswordValid) {
                return res.status(403).send({
                    error: 'Invalid login information.'
                })
            }

            const ref = jwtSignUserRefreshToken(user.toObject()) // fix not all info to go through, make it so cookies are verified and not sent again

            const as = jwtSignUserAccessToken(user.toObject())

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
            .send({
                success: true,
                message: 'Login successful!',
                user: {
                    username: user.username,
                    email: user.email
                }
            })
            
        } catch (err) {
            console.log(err)
            res.status(500).send({
                error: 'Invalid login information.'
            })
        }
    },
    async logout (req, res) {
        try{
            const ref = req.cookies.ref

            if (ref) {
                 let decodedToken

                try {
                    decodedToken = jwt.verify(ref, config.authentication.jwtRefreshSecret)
                } catch (err) {
                    return res.status(401).send({
                            error: 'Invalid refresh token' })
                }
    
                const { id, jwtV } = decodedToken
                    if (!id || !jwtV) {
                        return res.status(400).send({
                            error: 'Something went wrong!' })
                    }
    
                const jwtVValue = parseInt(jwtV, 10)
                    if (isNaN(jwtVValue)) {
                        return res.status(400).send({ 
                            error: 'Something went wrong!' })
                    }
    
                const user = await User.findById(id)
    
                if (!user) {
                    return res.status(404).send({
                            error: 'User not found' })
                    }
    
                user.jwtVersion = jwtVValue + 1

                await user.save()
            }
            res
            .clearCookie('as', { path: '/' })
            .clearCookie('ref', { path: '/refresh' })
            .status(200).send({
                message: 'User logged out successfully' })

        } catch (err) {
            res
            .clearCookie('as', { path: '/' })
            .clearCookie('ref', { path: '/refresh' })
            .status(500).send({
                message: 'There was a problem so you have been logged out only from this device' })
        }
    },
    async get_user (req, res) {
        const as = req.cookies.as

            if (!as) {
                return res.status(400).send({
                    error: 'Missing as' })
            }

            let decodedToken

            try {
                decodedToken = jwt.verify(as, config.authentication.jwtAccessSecret)
            } catch (err) {
                return res.status(401).send({
                        error: 'Invalid access token' })
            }

            const { id } = decodedToken
                if (!id) {
                    return res.status(400).send({
                        error: 'Something went wrong!' })
                }

            const user = await User.findById(id)

            if (!user) {
                return res.status(404).send({
                        error: 'User not found' })
                }
            return res.status(200).send({
                success: true,
                message: 'Login successful!',
                user: {
                    username: user.username,
                    email: user.email
                }
            })
    },
    async delete_account (req, res) {
        const ref = req.cookies.ref

        if (!ref) {
            return res.status(401).send({
                error: 'Missing refresh token'
            })
        }

        let decodedToken
        try {
            decodedToken = jwt.verify(ref, config.authentication.jwtRefreshSecret)
        } catch (err) {
            return res.status(401).send({
                error: 'Invalid refresh token'
            })
        }

        const { id, jwtV } = decodedToken
        if (!id || !jwtV) {
            return res.status(401).send({
                error: 'Something went wrong!'
            })
        }

        try {
            await User.findByIdAndDelete(id)
            res.clearCookie('as', { path: '/' })
            res.clearCookie('ref', { path: '/refresh' })
            res.status(200).send({
                message: 'Account deleted successfully'
            })
        } catch (err) {
            console.log(err)
            res.status(500).send({
                error: 'Error deleting account'
            })
        }
    }
  }