const express = require("express")
const cookieParser = require("cookie-parser")
const passport = require("passport")
const cors = require("cors")
const morgan = require("morgan")
const config = require("./config/config")
const mongoose = require('mongoose')

const app = express()

app.use(morgan("combined"))

app.use(express.json({ limit: '500mb' }))
app.use(cookieParser())

app.use(cors({
    origin: config.client.baseClientURL,
    credentials: true
}))

require("./routes")(app)

mongoose.connect(config.db.uri)

.then(() => {
    console.log("Connected to MongoDB")

    app.listen(config.portApp, () => {
        console.log(`Server started on port ${config.portApp}`)
    })
})