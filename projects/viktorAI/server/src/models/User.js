const bcrypt = (require("bcrypt"))
const { v4: uuidv4 } = require('uuid')
const config = require("../config/config")
const mongoose = require('mongoose')

const userSchema = new mongoose.Schema({
    _id: {
        type: String,
        default: uuidv4,
        required: true,
    },
    googleId: {
        type: String,
        unique: true,
        sparse: true,
        required: false,
    },
    username: {
        type: String,
        unique: true,
        required: true,
        trim: true
    },
    email: {
        type: String,
        unique: true,
        required: true,
        trim: true,
        validate: {
            validator: (email) => /^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$/.test(email),
            message: 'Invalid email format'
        }
    },
    password: {
        type: String,
        required: false
    },
    jwtVersion: {
        type: Number,
        default: 1
    }
}, {timestamps: true })

userSchema.pre('save', async function(next) {

    if (!this.isModified('password')) return next()

    try {
        const saltRounds = parseInt(config.salt)
        const salt = await bcrypt.genSalt(saltRounds)
        this.password = await bcrypt.hash(this.password, salt)
        next();
    } catch (error) {
        next(error)
    }
})

userSchema.methods.comparePassword = function(candidatePassword) {
    return bcrypt.compare(candidatePassword, this.password)
}

const User = mongoose.model('User', userSchema)

module.exports = User