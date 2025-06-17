const Joi = require("joi")

module.exports = {
    register (req, res, next) {
        const schema = Joi.object({
            username: Joi.string().alphanum().min(3).max(30),
            email: Joi.string().email(),
            password: Joi.string().pattern(new RegExp('^[\\s\\S]{8,60}$')).required()
        })
        const {error} = schema.validate(req.body);
        if (error) {
            switch (error.details[0].context.key) {
                case "username": 
                    res.status(400).send({
                        error: "You must provide a valid username"
                })
                break
                case "email":
                    res.status(400).send({
                        error: "You must provide a valid email address"
                    })
                break
                case "password":
                    res.status(400).send({
                        error: "You must provide a valid password"
                    })
                    break
                case "repeat_password":
                    res.status(400).send({
                        error: "Passwords must match"
                    })
                break
                default: 
                    res.status(400).send({
                        error: "Invalid registration information"
                    })
            }
        }
        else {
            next()
        }
    }
}