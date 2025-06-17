if (process.env.NODE_ENV !== 'production') {
    require('dotenv').config({ path: "./.env" })
}

module.exports = {
    salt: process.env.SALT,
    portApp: process.env.PORT,
    db: {
        uri: process.env.MONGODB_URI
    },
    authentication: {
    jwtAccessSecret: process.env.JWT_ACCESS_SECRET,
    jwtRefreshSecret: process.env.JWT_REFRESH_SECRET,
    apiAccessToken: process.env.API_ACCESS_TOKEN,
    },
    server: {
        baseServerURL: process.env.NODE_ENV === 'production' ? "https://api.re-helpr.nl" : "http://localhost:8080",
    },
    client: {
        baseClientURL: process.env.NODE_ENV === 'production' ? "https://www.re-helpr.nl" : "http://localhost:5001",
    },
    gemini: {
        apiKey: process.env.GEMINI_API_KEY,
    },
    chiselUrl: {
        url: process.env.CHISEL_URL,
    }
}